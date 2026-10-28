export const TITLEBAR_DRAG_THRESHOLD_PX = 5;
export const MIN_NATIVE_CONTENT_WIDTH_PX = 160;
export const MAX_NATIVE_CONTENT_WIDTH_PX = 2_400;
export const MIN_NATIVE_CONTENT_HEIGHT_PX = 50;
export const MAX_NATIVE_CONTENT_HEIGHT_PX = 10_000;

export function normalizeNativeContentWidth(width: number): number | null {
  if (!Number.isFinite(width) || width < 0) return null;
  return Math.min(MAX_NATIVE_CONTENT_WIDTH_PX, Math.max(MIN_NATIVE_CONTENT_WIDTH_PX, width));
}

export function normalizeNativeContentHeight(height: number): number | null {
  if (!Number.isFinite(height) || height < 0 || height > MAX_NATIVE_CONTENT_HEIGHT_PX) return null;
  return Math.max(MIN_NATIVE_CONTENT_HEIGHT_PX, height);
}

export function titlebarMovementExceedsDragThreshold(
  startX: number,
  startY: number,
  currentX: number,
  currentY: number,
): boolean {
  return Math.hypot(currentX - startX, currentY - startY) >= TITLEBAR_DRAG_THRESHOLD_PX;
}

export function shouldShowConnectionStatus(status: string): boolean {
  return status !== 'online';
}
