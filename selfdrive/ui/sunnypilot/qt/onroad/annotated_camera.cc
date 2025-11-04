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
  const int arrow_size = 80;   // Larger arrow indicator
  const int x_gap = 20;        // Gap between arrow and button

  // Position: to the LEFT of experimental button, vertically centered with it
  // Button is positioned at: rect.width() - UI_BORDER_SIZE - btn_size (left edge)
  // Arrow should be: button_left_edge - x_gap - arrow_size/2
  int arrow_x = rect.width() - UI_BORDER_SIZE - btn_size - x_gap - arrow_size / 2;
  int arrow_y = UI_BORDER_SIZE + btn_size / 2;  // Vertically centered with button center

  // Draw arrow pointing up-right (pointing toward destination)
  QPolygon arrow_shape;
  int half_size = arrow_size / 2;

  // Triangle pointing up
  arrow_shape << QPoint(arrow_x, arrow_y + half_size / 2)           // Bottom left
               << QPoint(arrow_x + half_size, arrow_y + half_size / 2)  // Bottom right
               << QPoint(arrow_x + half_size / 2, arrow_y - half_size);  // Top center

  painter.save();

  if (nav_active) {
    // Filled green arrow when navigation active
    painter.setPen(Qt::NoPen);
    painter.setBrush(QColor(0, 255, 0, 255));  // Bright green
    painter.drawPolygon(arrow_shape);
  } else {
    // Gray outline only when inactive
    painter.setPen(QPen(QColor(128, 128, 128, 150), 3));
    painter.setBrush(Qt::NoBrush);
    painter.drawPolygon(arrow_shape);
  }

  painter.restore();
}
