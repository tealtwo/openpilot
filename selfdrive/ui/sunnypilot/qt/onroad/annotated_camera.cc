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

  bool nav_active = false;
  if (sm.updated("navStateSP") || sm.valid("navStateSP")) {
    const auto nav_state = sm["navStateSP"].getNavStateSP();
    nav_active = nav_state.getActive();
  }

  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);
  drawNavigationStatusArrow(painter, rect(), nav_active);
}

void AnnotatedCameraWidgetSP::drawNavigationStatusArrow(QPainter &painter, const QRect &rect, bool nav_active) {
  const int btn_size = 192;  // Experimental button size
  const int arrow_size = 40;  // Small arrow indicator
  const int x_offset = 10;    // Gap from button
  const int y_offset = 10;    // Gap below button

  // Position: below and slightly left of experimental button
  int arrow_x = rect.width() - btn_size - x_offset - arrow_size / 2;
  int arrow_y = btn_size + y_offset + arrow_size / 2;

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
