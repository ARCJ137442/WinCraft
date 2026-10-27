//! Adapted from ExoMind now_workbench_overlay_commands.rs, commit ddb1ba1a.
//! Copyright (c) 2026 ExoMind Collective. Upstream license: CCOPL-1.0.
//! Geometry only; no business/profile storage is imported.
use crate::{Fault, Position, WorkAreaAnchor, WorkAreaCorner};
use std::convert::TryFrom;

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

/// Resolve a logical-pixel work-area anchor into physical desktop coordinates.
///
/// Margins are scaled with the target monitor's scale factor. If the requested
/// margin and window size cannot fit, the window is clamped to the work area's
/// leading edge; it is never placed outside solely because its size is larger.
pub fn resolve_work_area_anchor(
    anchor: WorkAreaAnchor,
    work: Rect,
    window_width: u32,
    window_height: u32,
    scale_factor: f64,
) -> Result<Position, Fault> {
    anchor.validate()?;
    if !scale_factor.is_finite() || !(0.5..=8.0).contains(&scale_factor) {
        return Err(Fault::new(
            "INVALID_WINDOW",
            "monitor scale factor must be finite and within 0.5..=8",
        ));
    }

    let margin_x = (anchor.margin_x * scale_factor).round() as i64;
    let margin_y = (anchor.margin_y * scale_factor).round() as i64;
    let work_left = i64::from(work.x);
    let work_top = i64::from(work.y);
    let work_right = work_left + i64::from(work.width);
    let work_bottom = work_top + i64::from(work.height);
    let window_width = i64::from(window_width);
    let window_height = i64::from(window_height);

    let (x, y) = match anchor.corner {
        WorkAreaCorner::TopLeft => (work_left + margin_x, work_top + margin_y),
        WorkAreaCorner::TopRight => (work_right - window_width - margin_x, work_top + margin_y),
        WorkAreaCorner::BottomLeft => {
            (work_left + margin_x, work_bottom - window_height - margin_y)
        }
        WorkAreaCorner::BottomRight => (
            work_right - window_width - margin_x,
            work_bottom - window_height - margin_y,
        ),
    };

    let max_x = (work_right - window_width).max(work_left);
    let max_y = (work_bottom - window_height).max(work_top);
    let x = x.clamp(work_left, max_x);
    let y = y.clamp(work_top, max_y);
    Ok(Position {
        x: i32::try_from(x).map_err(|_| Fault::new("INVALID_WINDOW", "anchor x overflow"))?,
        y: i32::try_from(y).map_err(|_| Fault::new("INVALID_WINDOW", "anchor y overflow"))?,
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    use crate::WorkAreaCorner;
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

    #[test]
    fn anchors_resolve_from_each_work_area_corner_with_monitor_scale() {
        let work = Rect {
            x: -1920,
            y: 40,
            width: 1920,
            height: 1040,
        };
        let resolve = |corner| {
            resolve_work_area_anchor(
                WorkAreaAnchor {
                    corner,
                    margin_x: 10.0,
                    margin_y: 12.0,
                },
                work,
                400,
                200,
                1.5,
            )
            .unwrap()
        };
        assert_eq!(
            resolve(WorkAreaCorner::TopLeft),
            Position { x: -1905, y: 58 }
        );
        assert_eq!(
            resolve(WorkAreaCorner::TopRight),
            Position { x: -415, y: 58 }
        );
        assert_eq!(
            resolve(WorkAreaCorner::BottomLeft),
            Position { x: -1905, y: 862 }
        );
        assert_eq!(
            resolve(WorkAreaCorner::BottomRight),
            Position { x: -415, y: 862 }
        );
    }

    #[test]
    fn anchor_is_clamped_when_window_or_margin_exceeds_work_area() {
        let position = resolve_work_area_anchor(
            WorkAreaAnchor {
                corner: WorkAreaCorner::BottomRight,
                margin_x: 100.0,
                margin_y: 100.0,
            },
            Rect {
                x: -800,
                y: 100,
                width: 320,
                height: 220,
            },
            500,
            300,
            1.0,
        )
        .unwrap();
        assert_eq!(position, Position { x: -800, y: 100 });
    }

    #[test]
    fn invalid_scale_is_rejected() {
        let result = resolve_work_area_anchor(
            WorkAreaAnchor {
                corner: WorkAreaCorner::TopLeft,
                margin_x: 0.0,
                margin_y: 0.0,
            },
            Rect {
                x: 0,
                y: 0,
                width: 100,
                height: 100,
            },
            10,
            10,
            f64::NAN,
        );
        assert_eq!(result.unwrap_err().code, "INVALID_WINDOW");
    }
}
