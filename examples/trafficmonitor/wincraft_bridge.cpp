#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdio>
#include <cstdint>
#include <cwchar>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

#include "vendor/PluginInterface.h"

namespace {

constexpr wchar_t kOutputEnvironment[] = L"WINCRAFT_TRAFFICMONITOR_OUT";
constexpr wchar_t kStatusEnvironment[] = L"WINCRAFT_TRAFFICMONITOR_STATUS";
constexpr wchar_t kVersionEnvironment[] = L"WINCRAFT_TRAFFICMONITOR_VERSION";
constexpr char kSchema[] = "wincraft.trafficmonitor.v1";
constexpr char kStatusSchema[] = "wincraft.trafficmonitor.bridge_status.v1";

std::wstring ReadEnvironmentPath(const wchar_t* name) {
    std::vector<wchar_t> buffer(32768);
    const DWORD length = GetEnvironmentVariableW(name, buffer.data(),
                                                 static_cast<DWORD>(buffer.size()));
    if (length == 0 || length >= buffer.size()) {
        return {};
    }
    return std::wstring(buffer.data(), length);
}

std::string ToUtf8(const wchar_t* text) {
    if (text == nullptr || *text == L'\0') {
        return {};
    }
    const int character_count = static_cast<int>(std::wcslen(text));
    const int required = WideCharToMultiByte(
        CP_UTF8, WC_ERR_INVALID_CHARS, text, character_count,
        nullptr, 0, nullptr, nullptr);
    if (required <= 0) {
        return {};
    }
    std::string result(static_cast<std::size_t>(required), '\0');
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, character_count,
                        result.data(), required, nullptr, nullptr);
    return result;
}

std::string EscapeJson(const std::string& value) {
    std::ostringstream escaped;
    for (const unsigned char character : value) {
        switch (character) {
            case '"': escaped << "\\\""; break;
            case '\\': escaped << "\\\\"; break;
            case '\b': escaped << "\\b"; break;
            case '\f': escaped << "\\f"; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default:
                if (character < 0x20) {
                    constexpr char hex[] = "0123456789abcdef";
                    escaped << "\\u00" << hex[character >> 4] << hex[character & 0x0f];
                } else {
                    escaped << static_cast<char>(character);
                }
        }
    }
    return escaped.str();
}

std::wstring FormatRate(unsigned long long bytes_per_second) {
    double value = static_cast<double>(bytes_per_second);
    const wchar_t* units[] = {L"B/s", L"KB/s", L"MB/s", L"GB/s"};
    constexpr std::size_t unit_count = sizeof(units) / sizeof(units[0]);
    std::size_t unit = 0;
    while (value >= 1024.0 && unit + 1 < unit_count) {
        value /= 1024.0;
        ++unit;
    }
    std::wostringstream formatted;
    if (unit == 0) {
        formatted << bytes_per_second;
    } else {
        formatted << std::fixed << std::setprecision(1) << value;
    }
    formatted << L' ' << units[unit];
    return formatted.str();
}

std::wstring FormatPercent(int value) {
    return value < 0 ? std::wstring{} : std::to_wstring(value) + L"%";
}

std::uint64_t UnixMilliseconds() {
    FILETIME file_time{};
    GetSystemTimeAsFileTime(&file_time);
    ULARGE_INTEGER ticks{};
    ticks.LowPart = file_time.dwLowDateTime;
    ticks.HighPart = file_time.dwHighDateTime;
    constexpr std::uint64_t kWindowsToUnixEpoch = 116444736000000000ULL;
    return (ticks.QuadPart - kWindowsToUnixEpoch) / 10000ULL;
}

bool WriteAtomically(const std::wstring& output_path, const std::string& json) {
    if (output_path.empty()) {
        return false;
    }
    const std::wstring temporary_path = output_path + L".tmp";
    FILE* file = nullptr;
    if (_wfopen_s(&file, temporary_path.c_str(), L"wb") != 0 || file == nullptr) {
        return false;
    }
    const std::size_t written = std::fwrite(json.data(), 1, json.size(), file);
    const bool flushed = std::fflush(file) == 0;
    const bool closed = std::fclose(file) == 0;
    if (written != json.size() || !flushed || !closed) {
        DeleteFileW(temporary_path.c_str());
        return false;
    }
    const bool moved = MoveFileExW(temporary_path.c_str(), output_path.c_str(),
                                   MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
    if (!moved) {
        DeleteFileW(temporary_path.c_str());
    }
    return moved;
}

class BridgeItem final : public IPluginItem {
public:
    const wchar_t* GetItemName() const override { return L"WinCraft bridge"; }
    const wchar_t* GetItemId() const override { return L"wincraft.bridge"; }
    const wchar_t* GetItemLableText() const override { return L"WinCraft"; }
    const wchar_t* GetItemValueText() const override { return L"read-only bridge"; }
    const wchar_t* GetItemValueSampleText() const override { return L"read-only bridge"; }
};

class TrafficMonitorBridge final : public ITMPlugin {
public:
    TrafficMonitorBridge()
        : output_path_(ReadEnvironmentPath(kOutputEnvironment)),
          status_path_(ReadEnvironmentPath(kStatusEnvironment)),
          version_fallback_(ReadEnvironmentPath(kVersionEnvironment)) {}

    IPluginItem* GetItem(int index) override {
        return index == 0 ? &item_ : nullptr;
    }

    void DataRequired() override {
        ++data_required_calls_;
        WriteStatus();
    }

    void OnMonitorInfo(const MonitorInfo& monitor_info) override {
        ++monitor_info_calls_;
        last_sample_write_ok_ = Publish(monitor_info);
        WriteStatus();
    }

    const wchar_t* GetInfo(PluginInfoIndex index) override {
        switch (index) {
            case TMI_NAME: return L"WinCraft read-only bridge";
            case TMI_DESCRIPTION: return L"Publishes selected TrafficMonitor readings to a local JSON file.";
            case TMI_AUTHOR: return L"WinCraft example";
            case TMI_COPYRIGHT: return L"Local prototype adapter";
            case TMI_VERSION: return L"0.1.0";
            case TMI_URL: return L"https://github.com/zhongyang219/TrafficMonitor";
            default: return L"";
        }
    }

    void OnInitialize(ITrafficMonitor* app) override {
        api_version_ = app == nullptr ? 0 : app->GetAPIVersion();
        if (app == nullptr || api_version_ < 1) {
            app_ = nullptr;
            WriteStatus();
            return;
        }
        app_ = app;
        WriteStatus();
    }

private:
    bool Publish(const MonitorInfo& monitor_info) {
        if (output_path_.empty()) {
            return false;
        }
        const wchar_t* version = app_ == nullptr ? nullptr : app_->GetVersion();
        if ((version == nullptr || *version == L'\0') && !version_fallback_.empty()) {
            version = version_fallback_.c_str();
        }
        const std::wstring download = FormatRate(monitor_info.down_speed);
        const std::wstring upload = FormatRate(monitor_info.up_speed);
        const std::wstring cpu = FormatPercent(monitor_info.cpu_usage);
        const std::wstring memory = FormatPercent(monitor_info.memory_usage);
        const std::wstring gpu = FormatPercent(monitor_info.gpu_usage);
        const auto field = [](const char* name, const wchar_t* value) {
            std::ostringstream json;
            json << "\"" << name << "\":";
            if (value == nullptr || *value == L'\0') {
                json << "null";
            } else {
                json << "\"" << EscapeJson(ToUtf8(value)) << "\"";
            }
            return json.str();
        };

        std::ostringstream json;
        const std::uint64_t next_generation = generation_ + 1;
        json << "{\"schema\":\"" << kSchema << "\",\"sampled_at_ms\":"
             << UnixMilliseconds() << ",\"generation\":" << next_generation << ","
             << field("app_version", version) << ","
             << field("download", download.c_str()) << ","
             << field("upload", upload.c_str()) << ","
             << field("cpu", cpu.empty() ? nullptr : cpu.c_str()) << ","
             << field("memory", memory.empty() ? nullptr : memory.c_str()) << ","
             << field("gpu", gpu.empty() ? nullptr : gpu.c_str()) << "}";
        if (!WriteAtomically(output_path_, json.str())) {
            return false;
        }
        generation_ = next_generation;
        return true;
    }

    void WriteStatus() const {
        if (status_path_.empty()) {
            return;
        }
        std::ostringstream json;
        json << "{\"schema\":\"" << kStatusSchema << "\",\"api_pointer_available\":"
             << (app_ == nullptr ? "false" : "true")
             << ",\"api_version\":" << api_version_
             << ",\"output_path_configured\":"
             << (output_path_.empty() ? "false" : "true")
             << ",\"data_required_calls\":" << data_required_calls_
             << ",\"monitor_info_calls\":" << monitor_info_calls_
             << ",\"generation\":" << generation_
             << ",\"last_sample_write_ok\":"
             << (last_sample_write_ok_ ? "true" : "false") << "}";
        WriteAtomically(status_path_, json.str());
    }

    BridgeItem item_;
    ITrafficMonitor* app_ = nullptr;
    std::wstring output_path_;
    std::wstring status_path_;
    std::wstring version_fallback_;
    int api_version_ = 0;
    std::uint64_t data_required_calls_ = 0;
    std::uint64_t monitor_info_calls_ = 0;
    std::uint64_t generation_ = 0;
    bool last_sample_write_ok_ = false;
};

TrafficMonitorBridge g_plugin;

}  // namespace

extern "C" __declspec(dllexport) ITMPlugin* TMPluginGetInstance() {
    return &g_plugin;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}
