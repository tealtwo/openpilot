/**
 * Copyright (c) TealTwo License Applies
 */
#include "selfdrive/ui/sunnypilot/qt/widgets/nav_preset_widget.h"

#include <QGridLayout>
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
  main_layout->setSpacing(20);

  QLabel *title = new QLabel(tr("Navigation Presets"));
  title->setStyleSheet("font-size: 56px; font-weight: 500;");
  main_layout->addWidget(title);

  // Create 3x2 grid of preset buttons
  QGridLayout *grid_layout = new QGridLayout();
  grid_layout->setHorizontalSpacing(30);
  grid_layout->setVerticalSpacing(50);  // Much more space between rows
  grid_layout->setContentsMargins(0, 20, 0, 0);

  for (int i = 0; i < PRESET_COUNT; i++) {
    int row = i / 3;
    int col = i % 3;

    // Container for button + label - fixed size to prevent overlap
    QWidget *preset_container = new QWidget();
    preset_container->setFixedSize(180, 230);  // Width x Height for button + label
    QVBoxLayout *preset_layout = new QVBoxLayout(preset_container);
    preset_layout->setSpacing(10);
    preset_layout->setContentsMargins(0, 0, 0, 0);

    // Round button
    QPushButton *btn = new QPushButton();
    btn->setFixedSize(140, 140);
    btn->setStyleSheet(R"(
      QPushButton {
        font-size: 65px;
        border-radius: 70px;
        background-color: #444444;
        border: none;
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
    preset_layout->addWidget(btn, 0, Qt::AlignHCenter);

    // Label below button - fixed height
    QLabel *label = new QLabel();
    label->setFixedSize(180, 70);  // Give enough space for 2 lines
    label->setStyleSheet("font-size: 26px; color: white;");
    label->setAlignment(Qt::AlignHCenter | Qt::AlignTop);
    label->setWordWrap(true);
    preset_labels[i] = label;
    preset_layout->addWidget(label, 0, Qt::AlignHCenter);

    grid_layout->addWidget(preset_container, row, col, Qt::AlignCenter);
  }

  main_layout->addLayout(grid_layout);
  main_layout->addStretch();

  setStyleSheet(R"(
    NavPresetWidget {
      background-color: #333333;
      border-radius: 10px;
    }
  )");

  setMinimumHeight(500);
  setMaximumHeight(800);
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
      preset_buttons[i]->setText("📍");
      preset_labels[i]->setText(presets[i].name);
    } else {
      preset_buttons[i]->setText("➕");
      preset_labels[i]->setText("Tap to\nconfigure");
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
