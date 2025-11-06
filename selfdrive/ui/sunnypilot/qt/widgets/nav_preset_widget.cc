/**
 * Copyright (c) TealTwo License Applies
 */
#include "selfdrive/ui/sunnypilot/qt/widgets/nav_preset_widget.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QTimer>
#include <QVBoxLayout>

#include "selfdrive/ui/sunnypilot/qt/widgets/address_input_dialog.h"

NavPresetWidget::NavPresetWidget(QWidget *parent) : QFrame(parent) {
  setupUI();
  loadPresets();
  refreshPresets();
}

void NavPresetWidget::setupUI() {
  QVBoxLayout *main_layout = new QVBoxLayout(this);
  main_layout->setContentsMargins(56, 40, 56, 40);
  main_layout->setSpacing(12);

  QLabel *title = new QLabel(tr("Navigation Presets"));
  title->setStyleSheet("font-size: 56px; font-weight: 500;");
  main_layout->addWidget(title);

  // Create 6 preset buttons
  for (int i = 0; i < PRESET_COUNT; i++) {
    QPushButton *btn = new QPushButton();
    btn->setMinimumHeight(85);
    btn->setMaximumHeight(95);
    btn->setStyleSheet(R"(
      QPushButton {
        font-size: 40px;
        font-weight: 400;
        border-radius: 10px;
        background-color: #444444;
        padding: 20px;
        text-align: left;
      }
      QPushButton:pressed {
        background-color: #555555;
      }
    )");

    QTimer *press_timer = new QTimer(this);
    press_timer->setSingleShot(true);
    press_timer->setInterval(500); // 500ms for long press

    connect(btn, &QPushButton::pressed, [press_timer]() {
      press_timer->start();
    });

    connect(btn, &QPushButton::released, [this, i, press_timer]() {
      if (press_timer->isActive()) {
        press_timer->stop();
        onPresetClicked(i);
      }
    });

    connect(press_timer, &QTimer::timeout, [this, i]() {
      configurePreset(i);
    });

    preset_buttons[i] = btn;
    main_layout->addWidget(btn);
  }

  setStyleSheet(R"(
    NavPresetWidget {
      background-color: #333333;
      border-radius: 10px;
    }
  )");

  setMinimumHeight(400);
  setMaximumHeight(700);
}

void NavPresetWidget::loadPresets() {
  QString json_str = QString::fromStdString(params.get("NavigationPresets"));
  if (json_str.isEmpty()) {
    // Initialize with empty presets
    for (int i = 0; i < PRESET_COUNT; i++) {
      presets[i] = Preset();
    }
    return;
  }

  QJsonDocument doc = QJsonDocument::fromJson(json_str.toUtf8());
  QJsonArray preset_array = doc.object()["presets"].toArray();

  for (int i = 0; i < PRESET_COUNT; i++) {
    if (i < preset_array.size()) {
      QJsonObject obj = preset_array[i].toObject();
      presets[i].name = obj["name"].toString();
      presets[i].address = obj["address"].toString();
      presets[i].latitude = obj["latitude"].toDouble();
      presets[i].longitude = obj["longitude"].toDouble();
      presets[i].configured = !presets[i].name.isEmpty();
    } else {
      presets[i] = Preset();
    }
  }
}

void NavPresetWidget::savePresets() {
  QJsonArray preset_array;

  for (int i = 0; i < PRESET_COUNT; i++) {
    if (presets[i].configured) {
      QJsonObject obj;
      obj["name"] = presets[i].name;
      obj["address"] = presets[i].address;
      obj["latitude"] = presets[i].latitude;
      obj["longitude"] = presets[i].longitude;
      preset_array.append(obj);
    }
  }

  QJsonObject root;
  root["presets"] = preset_array;

  QJsonDocument doc(root);
  params.put("NavigationPresets", doc.toJson(QJsonDocument::Compact).toStdString());
}

void NavPresetWidget::refreshPresets() {
  for (int i = 0; i < PRESET_COUNT; i++) {
    if (presets[i].configured) {
      preset_buttons[i]->setText(QString("📍 %1  →").arg(presets[i].name));
    } else {
      preset_buttons[i]->setText("➕ Tap to configure");
    }
  }
}

void NavPresetWidget::onPresetClicked(int index) {
  if (presets[index].configured) {
    // Navigate to preset
    navigateToPreset(index);
  } else {
    // Configure new preset
    configurePreset(index);
  }
}

void NavPresetWidget::configurePreset(int index) {
  QString name;
  double latitude, longitude;
  QString address;

  if (AddressInputDialog::getAddress(this, name, latitude, longitude, address)) {
    presets[index].name = name;
    presets[index].address = address;
    presets[index].latitude = latitude;
    presets[index].longitude = longitude;
    presets[index].configured = true;

    savePresets();
    refreshPresets();
  }
}

void NavPresetWidget::navigateToPreset(int index) {
  QJsonObject destination;
  destination["name"] = presets[index].name;
  destination["latitude"] = presets[index].latitude;
  destination["longitude"] = presets[index].longitude;

  QJsonDocument doc(destination);
  params.put("NavigationDestination", doc.toJson(QJsonDocument::Compact).toStdString());
}
