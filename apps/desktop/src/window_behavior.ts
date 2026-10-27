export const TITLEBAR_DRAG_THRESHOLD_PX = 5;

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
