//! Adapted from ExoMind now_workbench_overlay_commands.rs, commit ddb1ba1a.
//! Copyright (c) 2026 ExoMind Collective. Upstream license: CCOPL-1.0.
//! Geometry only; no business/profile storage is imported.
#[derive(Clone, Copy, Debug)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}
pub fn intersects(a: Rect, b: Rect) -> bool {
    // i64 prevents overflow on hostile/prototype coordinate inputs.
    let (ax, ay, bx, by) = (
        i64::from(a.x),
        i64::from(a.y),
        i64::from(b.x),
        i64::from(b.y),
    );
    ax < bx + i64::from(b.width)
        && ax + i64::from(a.width) > bx
        && ay < by + i64::from(b.height)
        && ay + i64::from(a.height) > by
}
pub fn hidden_sentinel(x: i32, y: i32) -> bool {
    x <= -30_000 && y <= -30_000
}
pub fn bottom_right(work: Rect, width: u32, height: u32) -> (i32, i32) {
    (
        work.x
            .saturating_add((i64::from(work.width) - i64::from(width) - 24).max(0) as i32),
        work.y
            .saturating_add((i64::from(work.height) - i64::from(height) - 24).max(0) as i32),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn anchor() {
        assert_eq!(
            bottom_right(
                Rect {
                    x: 0,
                    y: 0,
                    width: 1920,
                    height: 1080
                },
                412,
                490
            ),
            (1484, 566)
        );
    }
    #[test]
    fn negative_monitor_is_valid() {
        assert!(!hidden_sentinel(-1920, 40));
        assert!(intersects(
            Rect {
                x: -1600,
                y: 120,
                width: 412,
                height: 490
            },
            Rect {
                x: -1920,
                y: 0,
                width: 1920,
                height: 1080
            }
        ));
        assert!(hidden_sentinel(-32000, -32000));
    }
}
