'''Read vendor quota sources through fixed, opt-in, read-only HTTPS adapters.
- 🎯复用 TeamSense Worker 已验证过的供应商端点与字段映射，但不调用 TeamSense 服务。
- 📌仅在调用方显式启用并提供本机密钥后发起固定 GET；密钥、原始响应与账户标识不进入投影。
- 🤖由 Agent 编写，未经人工逐行审阅。
'''
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping


# * === 常量池 === * #

DEEPSEEK_BALANCE_URL: str = 'https://api.deepseek.com/user/balance'
'''📍TeamSense Worker 已使用的固定 DeepSeek 只读额度端点'''

MINIMAX_QUOTA_URL: str = 'https://api.minimaxi.com/v1/token_plan/remains'
'''📍TeamSense Worker 已使用的固定 MiniMax 只读额度端点'''

REQUEST_TIMEOUT_SECONDS: int = 8
'''📜供应商请求超时'''

MAX_RESPONSE_BYTES: int = 262_144
'''📜供应商响应最大字节数'''

MAX_API_KEY_CHARS: int = 4096
'''📜本机 API key 最大长度'''

MAX_MODELS: int = 8
'''📜MiniMax 面板最多呈现的模型数'''

MAX_BALANCES: int = 4
'''📜DeepSeek 面板最多呈现的币种数'''

MAX_SAFE_INTEGER: int = 9_007_199_254_740_991
'''📜JSON 数值可安全呈现的最大整数'''

MAX_WINDOW_SECONDS: int = 31_536_000
'''📜额度周期最大一年'''

MAX_TIMESTAMP_MILLIS: int = 253_402_300_799_000
'''📜可表示到 UTC 年 9999 的毫秒时间戳上限'''

MICROS_PER_UNIT: int = 1_000_000
'''📐DeepSeek 余额从主币种单位转换到微单位'''

DEEPSEEK_API_KEY_ENV: str = 'DEEPSEEK_API_KEY'
'''🔧显式启用 DeepSeek 时读取的进程环境变量名'''

MINIMAX_API_KEY_ENV: str = 'MINIMAX_API_KEY'
'''🔧显式启用 MiniMax 时读取的进程环境变量名'''

SOURCE_ERROR_LABELS: dict[str, str] = {
    'NOT_CONFIGURED': '本机密钥未配置',
    'AUTH_REJECTED': '供应商未接受本机密钥',
    'REDIRECT_BLOCKED': '已拒绝非预期重定向',
    'UPSTREAM_REJECTED': '供应商拒绝额度读取',
    'REQUEST_TIMEOUT': '供应商请求超时',
    'NETWORK_ERROR': '供应商网络读取失败',
    'RESPONSE_TOO_LARGE': '供应商响应超过本机上限',
    'INVALID_JSON': '供应商响应不是有效 JSON',
    'INVALID_RESPONSE': '供应商响应结构无效',
}


class ProviderQuotaError(RuntimeError):
    '''不包含密钥、响应正文或 URL 参数的本机供应商读取错误。'''

    def __init__(self, code: str) -> None:
        self.code: str = code if code in SOURCE_ERROR_LABELS else 'NETWORK_ERROR'
        super().__init__(self.code)


class __NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    '''阻止携带 bearer token 的请求被转发到其他主机。'''

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def __validate_api_key(api_key: str) -> None:
    '''验证本机显式配置的 API key，不将其写入异常文本。'''
    if (
        not api_key
        or len(api_key) > MAX_API_KEY_CHARS
        or any(char.isspace() for char in api_key)
    ):
        raise ProviderQuotaError('NOT_CONFIGURED')


def __fetch_json(
    *,
    url: str,
    api_key: str,
    include_content_type: bool,
    opener_factory: Callable[..., Any] = urllib.request.build_opener,
) -> Any:
    '''通过固定 HTTPS URL 发起有界 GET，并只返回已解析 JSON。'''
    __validate_api_key(api_key)
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    if include_content_type:
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, headers=headers, method='GET')
    opener = opener_factory(__NoRedirectHandler())
    try:
        response = opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            raise ProviderQuotaError('AUTH_REJECTED') from None
        if 300 <= error.code < 400:
            raise ProviderQuotaError('REDIRECT_BLOCKED') from None
        raise ProviderQuotaError('UPSTREAM_REJECTED') from None
    except TimeoutError:
        raise ProviderQuotaError('REQUEST_TIMEOUT') from None
    except (urllib.error.URLError, OSError):
        raise ProviderQuotaError('NETWORK_ERROR') from None

    try:
        with response:
            status = getattr(response, 'status', 200)
            if status in {401, 403}:
                raise ProviderQuotaError('AUTH_REJECTED')
            if 300 <= status < 400:
                raise ProviderQuotaError('REDIRECT_BLOCKED')
            if status != 200:
                raise ProviderQuotaError('UPSTREAM_REJECTED')
            content_length = response.headers.get('Content-Length')
            if content_length is not None:
                try:
                    if int(content_length) > MAX_RESPONSE_BYTES:
                        raise ProviderQuotaError('RESPONSE_TOO_LARGE')
                except ValueError:
                    raise ProviderQuotaError('INVALID_RESPONSE') from None
            encoded = response.read(MAX_RESPONSE_BYTES + 1)
    except ProviderQuotaError:
        raise
    except (TimeoutError, urllib.error.URLError, OSError):
        raise ProviderQuotaError('NETWORK_ERROR') from None
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise ProviderQuotaError('RESPONSE_TOO_LARGE')
    try:
        return json.loads(encoded.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProviderQuotaError('INVALID_JSON') from None


def __decimal_micros(value: Any) -> int:
    '''将供应商十进制余额精确转换为最多六位小数的微单位。'''
    match = (
        re.fullmatch(r'([+-]?)(\d+)(?:\.(\d{1,6}))?', value)
        if isinstance(value, str) and len(value) <= 64
        else None
    )
    if match is None:
        raise ProviderQuotaError('INVALID_RESPONSE')
    sign, whole, fraction = match.groups()
    amount = int(whole) * MICROS_PER_UNIT + int((fraction or '').ljust(6, '0'))
    if amount > MAX_SAFE_INTEGER:
        raise ProviderQuotaError('INVALID_RESPONSE')
    return -amount if sign == '-' else amount


def __utc_now(now: datetime | None) -> datetime:
    '''返回有时区的 UTC 时间；测试可注入固定时间。'''
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError('now must include a timezone')
    return observed.astimezone(timezone.utc)


def __observed_label(now: datetime | None) -> str:
    '''生成唯一的本机读取时间戳。'''
    return __utc_now(now).isoformat(timespec='seconds').replace('+00:00', 'Z')


def fetch_deepseek_balance(
    api_key: str,
    *,
    opener_factory: Callable[..., Any] = urllib.request.build_opener,
    now: datetime | None = None,
) -> dict[str, Any]:
    '''读取并规整 DeepSeek 的本机授权余额。'''
    raw = __fetch_json(
        url=DEEPSEEK_BALANCE_URL,
        api_key=api_key,
        include_content_type=False,
        opener_factory=opener_factory,
    )
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get('is_available'), bool)
    ):
        raise ProviderQuotaError('INVALID_RESPONSE')
    raw_balances = raw.get('balance_infos')
    if not isinstance(raw_balances, list):
        raise ProviderQuotaError('INVALID_RESPONSE')
    balances: list[dict[str, int | str]] = []
    seen_currencies: set[str] = set()
    for item in raw_balances:
        if not isinstance(item, dict):
            raise ProviderQuotaError('INVALID_RESPONSE')
        currency = item.get('currency')
        if (
            not isinstance(currency, str)
            or currency not in {'CNY', 'USD'}
            or currency in seen_currencies
        ):
            raise ProviderQuotaError('INVALID_RESPONSE')
        seen_currencies.add(currency)
        balances.append(
            {
                'currency': currency,
                'totalMicros': __decimal_micros(item.get('total_balance')),
                'grantedMicros': __decimal_micros(item.get('granted_balance')),
                'toppedUpMicros': __decimal_micros(item.get('topped_up_balance')),
            }
        )
        if len(balances) >= MAX_BALANCES:
            break
    fetched_at = __observed_label(now)
    return {
        'balance': {
            'fetchedAt': fetched_at,
            'isAvailable': raw['is_available'],
            'balances': balances,
        },
        'meta': {
            'freshness': 'fresh',
            'upstreamState': 'healthy',
            'fetchedAt': fetched_at,
        },
    }


def __finite_number(value: Any) -> float | None:
    '''读取有限数字或严格可转换的非空十进制字符串。'''
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            return None
        return (
            number
            if number == number and abs(number) != float('inf')
            else None
        )
    if isinstance(value, str) and value.strip():
        try:
            number = float(value)
        except (OverflowError, ValueError):
            return None
        return (
            number
            if number == number and abs(number) != float('inf')
            else None
        )
    return None


def __non_negative_integer(value: Any) -> int | None:
    '''只接受可精确表示的非负整数。'''
    number = __finite_number(value)
    if (
        number is None
        or number < 0
        or not number.is_integer()
        or number > MAX_SAFE_INTEGER
    ):
        return None
    return int(number)


def __epoch_millis(value: float) -> float:
    '''把秒或毫秒 epoch 归一化为毫秒。'''
    return value * 1000 if value < 1_000_000_000_000 else value


def __iso_from_epoch_millis(value: float) -> str | None:
    '''将范围内的 Unix 毫秒时间转换成 UTC RFC3339。'''
    if value <= 0 or value > MAX_TIMESTAMP_MILLIS:
        return None
    try:
        return (
            datetime.fromtimestamp(value / 1000, timezone.utc)
            .isoformat(timespec='seconds')
            .replace('+00:00', 'Z')
        )
    except (OverflowError, OSError, ValueError):
        return None


def __minimax_window(
    raw: Mapping[str, Any],
    *,
    prefix: str,
    fetched_at: datetime,
    not_in_plan: bool,
) -> dict[str, Any]:
    '''按 MiniMax 的窗口状态和时间字段生成不推算的额度窗口。'''
    status = __finite_number(raw.get(f'{prefix}_status'))
    raw_percent = __finite_number(raw.get(f'{prefix}_remaining_percent'))
    valid_percent = raw_percent if raw_percent is not None and 0 <= raw_percent <= 100 else None
    is_weekly = prefix == 'current_weekly'
    if not_in_plan:
        state = 'not_in_plan'
    elif status == 2:
        state = 'exhausted'
    elif status == 3 and is_weekly:
        state = 'unlimited'
    elif status is not None and status != 1:
        state = 'unknown'
    elif valid_percent is not None:
        state = 'metered'
    else:
        state = 'unknown'
    remaining_percent = (
        0 if state == 'exhausted' else valid_percent if state == 'metered' else None
    )

    start_key = 'weekly_start_time' if is_weekly else 'start_time'
    end_key = 'weekly_end_time' if is_weekly else 'end_time'
    remains_key = 'weekly_remains_time' if is_weekly else 'remains_time'
    start = __finite_number(raw.get(start_key))
    end = __finite_number(raw.get(end_key))
    window_seconds = None
    resets_at = None
    if start is not None and end is not None and end > start:
        start_ms = __epoch_millis(start)
        end_ms = __epoch_millis(end)
        seconds = (end_ms - start_ms) / 1000
        if 0 < seconds <= MAX_WINDOW_SECONDS:
            window_seconds = seconds
        resets_at = __iso_from_epoch_millis(end_ms)
    if resets_at is None and not_in_plan is False:
        remains_ms = __finite_number(raw.get(remains_key))
        if remains_ms is not None and remains_ms >= 0:
            reset_ms = fetched_at.timestamp() * 1000 + remains_ms
            resets_at = __iso_from_epoch_millis(reset_ms)

    total = __non_negative_integer(raw.get(f'{prefix}_total_count'))
    usage_key = (
        f'{prefix}_total_count'
        if state == 'exhausted'
        else f'{prefix}_usage_count'
    )
    usage = __non_negative_integer(raw.get(usage_key))
    used_count = None
    remaining_count = None
    total_count = None
    if (
        total is not None
        and total > 0
        and usage is not None
        and usage <= total
        and remaining_percent is not None
    ):
        remaining_if_used = ((total - usage) / total) * 100
        remaining_if_remaining = (usage / total) * 100
        if abs(remaining_if_used - remaining_percent) <= 1:
            used_count = usage
            remaining_count = total - usage
            total_count = total
        elif abs(remaining_if_remaining - remaining_percent) <= 1:
            used_count = total - usage
            remaining_count = usage
            total_count = total
    return {
        'state': state,
        'windowSeconds': window_seconds,
        'remainingPercent': remaining_percent,
        'usedCount': used_count,
        'remainingCount': remaining_count,
        'totalCount': total_count,
        'resetsAt': None if not_in_plan else resets_at,
    }


def __model_display_name(key: str) -> str:
    '''把 MiniMax 产品类别 key 映射为紧凑显示名。'''
    normalized = key.lower()
    if normalized == 'general' or 'minimax-m' in normalized:
        return '语言模型'
    if normalized == 'video':
        return '视频'
    if normalized == 'image':
        return '图像'
    if normalized in {'speech', 'audio'}:
        return '语音'
    return key[:80]


def fetch_minimax_quota(
    api_key: str,
    *,
    opener_factory: Callable[..., Any] = urllib.request.build_opener,
    now: datetime | None = None,
) -> dict[str, Any]:
    '''读取并规整 MiniMax 的本机授权额度窗口。'''
    raw = __fetch_json(
        url=MINIMAX_QUOTA_URL,
        api_key=api_key,
        include_content_type=True,
        opener_factory=opener_factory,
    )
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get('base_resp'), dict)
    ):
        raise ProviderQuotaError('INVALID_RESPONSE')
    base_response = raw['base_resp']
    if __finite_number(base_response.get('status_code')) != 0:
        raise ProviderQuotaError('UPSTREAM_REJECTED')
    raw_models = raw.get('model_remains')
    if not isinstance(raw_models, list):
        raise ProviderQuotaError('INVALID_RESPONSE')
    observed = __utc_now(now)
    models: list[dict[str, Any]] = []
    omitted_models = max(0, len(raw_models) - MAX_MODELS)
    for item in raw_models[:MAX_MODELS]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get('model_name'), str)
        ):
            raise ProviderQuotaError('INVALID_RESPONSE')
        key = item['model_name'].strip()
        if not key:
            raise ProviderQuotaError('INVALID_RESPONSE')
        not_in_plan = (
            __finite_number(item.get('current_interval_status')) == 3
            and __finite_number(item.get('current_weekly_status')) == 3
            and __finite_number(item.get('current_interval_total_count')) == 0
            and __finite_number(item.get('current_weekly_total_count')) == 0
        )
        models.append(
            {
                'key': key[:80],
                'name': __model_display_name(key),
                'interval': __minimax_window(
                    item,
                    prefix='current_interval',
                    fetched_at=observed,
                    not_in_plan=not_in_plan,
                ),
                'weekly': __minimax_window(
                    item,
                    prefix='current_weekly',
                    fetched_at=observed,
                    not_in_plan=not_in_plan,
                ),
            }
        )
    fetched_at = __observed_label(observed)
    return {
        'quota': {
            'fetchedAt': fetched_at,
            'isAvailable': bool(models),
            'models': models,
            'omittedModelCount': omitted_models,
        },
        'meta': {'freshness': 'fresh', 'upstreamState': 'healthy', 'fetchedAt': fetched_at},
    }


def __source_error_snapshot(
    *,
    previous: Any,
    data_key: str,
    error_code: str,
) -> dict[str, Any]:
    '''保留同一运行期的脱敏 last-good 数据，并把新鲜度标为陈旧。'''
    last_good = previous if isinstance(previous, Mapping) else {}
    prior_data = last_good.get(data_key)
    prior_meta = last_good.get('meta') if isinstance(last_good.get('meta'), Mapping) else {}
    has_last_good = isinstance(prior_data, Mapping) and bool(prior_data)
    return {
        data_key: prior_data if has_last_good else None,
        'meta': {
            'freshness': 'stale' if has_last_good else 'empty',
            'upstreamState': 'offline' if error_code != 'NOT_CONFIGURED' else 'unknown',
            'fetchedAt': prior_meta.get('fetchedAt') if has_last_good else None,
            'errorCode': error_code,
        },
    }


def refresh_local_sources(
    *,
    deepseek_enabled: bool,
    minimax_enabled: bool,
    previous: Mapping[str, Any] | None,
    environment: Mapping[str, str] | None = None,
    opener_factory: Callable[..., Any] = urllib.request.build_opener,
    now: datetime | None = None,
) -> dict[str, Any]:
    '''只刷新明确启用的供应商来源；未启用时不读取对应密钥环境变量。'''
    env = os.environ if environment is None else environment
    prior = previous if isinstance(previous, Mapping) else {}
    projection: dict[str, Any] = dict(prior)
    for enabled, source, data_key, env_key, fetcher in (
        (deepseek_enabled, 'deepseek', 'balance', DEEPSEEK_API_KEY_ENV, fetch_deepseek_balance),
        (minimax_enabled, 'minimax', 'quota', MINIMAX_API_KEY_ENV, fetch_minimax_quota),
    ):
        previous_source = prior.get(source)
        if not enabled:
            projection[source] = __source_error_snapshot(
                previous=previous_source,
                data_key=data_key,
                error_code='NOT_ENABLED',
            )
            continue
        api_key = env.get(env_key, '')
        if not api_key:
            projection[source] = __source_error_snapshot(
                previous=previous_source,
                data_key=data_key,
                error_code='NOT_CONFIGURED',
            )
            continue
        try:
            projection[source] = fetcher(api_key, opener_factory=opener_factory, now=now)
        except ProviderQuotaError as error:
            projection[source] = __source_error_snapshot(
                previous=previous_source,
                data_key=data_key,
                error_code=error.code,
            )
    projection['sources'] = [
        source
        for source, enabled in (
            ('deepseek_balance', deepseek_enabled),
            ('minimax_quota', minimax_enabled),
        )
        if enabled
    ]
    return projection
