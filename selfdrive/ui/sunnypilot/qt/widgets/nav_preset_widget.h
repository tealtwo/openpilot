/**
 * Copyright (c) TealTwo License Applies
 */
#pragma once

#include <QFrame>
#include <QPushButton>
#include <QWidget>
#include <array>

#include "common/params.h"

class NavPresetWidget : public QFrame {
  Q_OBJECT

public:
  explicit NavPresetWidget(QWidget* parent = nullptr);

private slots:
  void onPresetClicked(int index);
  void configurePreset(int index);
  void refreshPresets();

private:
  static constexpr int PRESET_COUNT = 6;

  struct Preset {
    QString name;
    QString address;
    double latitude = 0.0;
    double longitude = 0.0;
    bool configured = false;
  };

  Params params;
  std::array<Preset, PRESET_COUNT> presets;
  std::array<QPushButton*, PRESET_COUNT> preset_buttons;

  void loadPresets();
  void savePresets();
  void navigateToPreset(int index);
  void setupUI();
};
