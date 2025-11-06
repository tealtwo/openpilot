/**
 * Copyright (c) TealTwo License Applies
 */
#pragma once

#include <QDialog>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QString>
#include <QTimer>
#include <QVBoxLayout>
#include <QWidget>
#include <vector>

#include "common/params.h"
#include "selfdrive/ui/qt/widgets/keyboard.h"

class AddressInputDialog : public QDialog {
  Q_OBJECT

public:
  explicit AddressInputDialog(QWidget *parent);
  static bool getAddress(QWidget *parent, QString &outName, double &outLat,
                        double &outLon, QString &outAddress);

private slots:
  void onTextChanged(const QString &text);
  void onGeocodeFinished(QNetworkReply *reply);
  void onResultSelected(QListWidgetItem *item);
  void handleCancel();

private:
  struct GeocodingResult {
    QString display_name;
    QString address;
    double latitude;
    double longitude;
  };

  Params params;
  QLineEdit *address_input;
  QListWidget *results_list;
  Keyboard *keyboard;
  QLabel *title_label;
  QNetworkAccessManager *network_manager;
  QTimer *debounce_timer;
  std::vector<GeocodingResult> results;

  bool result_selected;
  QString selected_address;
  double selected_lat;
  double selected_lon;

  void geocodeAddress(const QString &query);
  void displayResults(const QJsonArray &features);
  void setupUI();
};
