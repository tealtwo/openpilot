/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/onroad/annotated_camera.h"

#include <QPainter>

AnnotatedCameraWidgetSP::AnnotatedCameraWidgetSP(VisionStreamType type, QWidget *parent)
    : AnnotatedCameraWidget(type, parent) {
}

void AnnotatedCameraWidgetSP::updateState(const UIState &s) {
  AnnotatedCameraWidget::updateState(s);
}

void AnnotatedCameraWidgetSP::showEvent(QShowEvent *event) {
  AnnotatedCameraWidget::showEvent(event);
  ui_update_params_sp(uiState());
  uiStateSP()->reset_onroad_sleep_timer(OnroadTimerStatusToggle::RESUME);
}

void AnnotatedCameraWidgetSP::hideEvent(QHideEvent *event) {
  AnnotatedCameraWidget::hideEvent(event);
  uiStateSP()->reset_onroad_sleep_timer(OnroadTimerStatusToggle::PAUSE);
}

void AnnotatedCameraWidgetSP::paintGL() {
  // Call base class rendering first
  AnnotatedCameraWidget::paintGL();

  // Draw navigation status arrow
  UIState *s = uiState();
  SubMaster &sm = *(s->sm);

  // Read current navigation state (don't check updated, just read current value)
  const auto nav_state = sm["navStateSP"].getNavStateSP();
  bool nav_active = nav_state.getActive();

  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  drawNavigationStatusArrow(painter, rect(), nav_active);
}

void AnnotatedCameraWidgetSP::drawNavigationStatusArrow(QPainter &painter, const QRect &rect, bool nav_active) {
  // btn_size is defined globally in buttons.h
  const int arrow_size = 100;  // Larger arrow indicator
  const int x_gap = 20;        // Gap between arrow and button

  // Position: to the LEFT of experimental button, vertically centered with it
  // Button is positioned at: rect.width() - UI_BORDER_SIZE - btn_size (left edge)
  // Arrow should be: button_left_edge - x_gap - arrow_size/2
  int arrow_x = rect.width() - UI_BORDER_SIZE - btn_size - x_gap - arrow_size / 2;
  int arrow_y = UI_BORDER_SIZE + btn_size / 2;  // Vertically centered with button center

  // Draw navigation arrow shape with clean V-notch at bottom
  QPolygon arrow_shape;

  int cx = arrow_x;  // Center X
  int tip_y = arrow_y - arrow_size / 2;      // Top tip
  int bottom_y = arrow_y + arrow_size / 2;   // Bottom edge
  int notch_center_y = arrow_y + arrow_size * 0.15;  // Center of V-notch (cuts upward into arrow)

  int half_width = arrow_size * 0.4;         // Half width at widest point

  // Navigation arrow with V-notch indenting upward into arrow body (5 points)
  arrow_shape << QPoint(cx, tip_y)                          // Tip (top center)
               << QPoint(cx + half_width, bottom_y)         // Bottom right corner
               << QPoint(cx + half_width * 0.3, bottom_y)   // Right edge at bottom
               << QPoint(cx, notch_center_y)                // Center of V-notch (indents UP into arrow)
               << QPoint(cx - half_width * 0.3, bottom_y)   // Left edge at bottom
               << QPoint(cx - half_width, bottom_y);        // Bottom left corner

  painter.save();

  if (nav_active) {
    // Filled green arrow when navigation active
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor(0, 255, 0, 255));  // Bright green
    painter.drawPolygon(arrow_shape);
  } else {
    // Gray outline only when inactive
    painter.setPen(QPen(QColor(128, 128, 128, 150), 4));
    painter.setBrush(Qt::NoBrush);
    painter.drawPolygon(arrow_shape);
  }

  painter.restore();
}
