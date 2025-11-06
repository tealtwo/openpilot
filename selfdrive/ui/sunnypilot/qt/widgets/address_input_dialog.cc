/**
 * Copyright (c) TealTwo License Applies
 */
#include "selfdrive/ui/sunnypilot/qt/widgets/address_input_dialog.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkRequest>
#include <QPushButton>
#include <QUrl>
#include <QVBoxLayout>

#include "selfdrive/ui/qt/qt_window.h"
#include "selfdrive/ui/qt/widgets/input.h"

AddressInputDialog::AddressInputDialog(QWidget *parent) : QDialog(parent) {
  result_selected = false;
  selected_lat = 0.0;
  selected_lon = 0.0;

  network_manager = new QNetworkAccessManager(this);
  connect(network_manager, &QNetworkAccessManager::finished,
          this, &AddressInputDialog::onGeocodeFinished);

  debounce_timer = new QTimer(this);
  debounce_timer->setSingleShot(true);
  debounce_timer->setInterval(500);  // 500ms debounce
  connect(debounce_timer, &QTimer::timeout, this, [this]() {
    if (!address_input->text().isEmpty()) {
      geocodeAddress(address_input->text());
    }
  });

  setupUI();
}

void AddressInputDialog::setupUI() {
  setStyleSheet(R"(
    * {
      outline: none;
      color: #1C1C1E;
      font-family: Inter;
    }
    AddressInputDialog {
      background-color: #FDF6E3;
    }
  )");

  QVBoxLayout *main_layout = new QVBoxLayout(this);
  main_layout->setContentsMargins(40, 40, 40, 40);
  main_layout->setSpacing(25);

  // Title
  title_label = new QLabel(tr("Enter Destination Address"));
  title_label->setStyleSheet("font-size: 90px; font-weight: bold;");
  main_layout->addWidget(title_label, 0, Qt::AlignTop);

  // Address input field
  address_input = new QLineEdit();
  address_input->setStyleSheet(R"(
    QLineEdit {
      background-color: white;
      border: 2px solid #CCCCCC;
      border-radius: 10px;
      padding: 25px;
      font-size: 55px;
    }
    QLineEdit:focus {
      border: 2px solid #465BEA;
    }
  )");
  connect(address_input, &QLineEdit::textChanged, this, &AddressInputDialog::onTextChanged);
  main_layout->addWidget(address_input);

  // Results list
  results_list = new QListWidget();
  results_list->setStyleSheet(R"(
    QListWidget {
      background-color: white;
      border: 2px solid #CCCCCC;
      border-radius: 10px;
      font-size: 40px;
    }
    QListWidget::item {
      padding: 20px;
      border-bottom: 1px solid #EEEEEE;
    }
    QListWidget::item:selected {
      background-color: #465BEA;
      color: white;
    }
  )");
  results_list->setMinimumHeight(400);
  results_list->setMaximumHeight(500);
  results_list->hide();  // Hidden until results available
  connect(results_list, &QListWidget::itemClicked, this, &AddressInputDialog::onResultSelected);
  main_layout->addWidget(results_list);

  main_layout->addStretch();

  // Cancel button
  QPushButton *cancel_btn = new QPushButton(tr("Cancel"));
  cancel_btn->setStyleSheet(R"(
    QPushButton {
      background-color: #CCCCCC;
      border-radius: 10px;
      padding: 30px;
      font-size: 50px;
      font-weight: 500;
    }
    QPushButton:pressed {
      background-color: #BBBBBB;
    }
  )");
  connect(cancel_btn, &QPushButton::clicked, this, &AddressInputDialog::handleCancel);
  main_layout->addWidget(cancel_btn);

  // Keyboard
  keyboard = new Keyboard(this);
  connect(keyboard, &Keyboard::emitBackspace, this, [this]() {
    address_input->backspace();
  });
  connect(keyboard, &Keyboard::emitKey, this, [this](const QString &key) {
    address_input->insert(key.left(1));
  });
  main_layout->addWidget(keyboard, 2, Qt::AlignBottom);
}

bool AddressInputDialog::getAddress(QWidget *parent, QString &outName,
                                    double &outLat, double &outLon, QString &outAddress) {
  AddressInputDialog d(parent);
  d.setModal(true);
  setMainWindow(&d);
  const int ret = d.exec();

  if (ret && d.result_selected) {
    outAddress = d.selected_address;
    outLat = d.selected_lat;
    outLon = d.selected_lon;

    // Ask for custom name
    QString name = InputDialog::getText("Preset Name", parent,
                                       "Enter a name for this destination (e.g., Home, Work)");
    if (name.isEmpty()) {
      return false;
    }
    outName = name;
    return true;
  }

  return false;
}

void AddressInputDialog::onTextChanged(const QString &text) {
  // Hide results while typing
  results_list->hide();
  results.clear();

  // Restart debounce timer
  if (!text.isEmpty()) {
    debounce_timer->start();
  } else {
    debounce_timer->stop();
  }
}

void AddressInputDialog::geocodeAddress(const QString &query) {
  QString token = QString::fromStdString(params.get("MAPBOX_TOKEN"));
  if (token.isEmpty()) {
    results_list->clear();
    results_list->addItem(tr("Error: Mapbox token not configured"));
    results_list->show();
    return;
  }

  QString encoded_query = QUrl::toPercentEncoding(query);
  QString url = QString("https://api.mapbox.com/geocoding/v5/mapbox.places/%1.json"
                       "?access_token=%2&limit=5&types=address,poi")
                       .arg(encoded_query)
                       .arg(token);

  QNetworkRequest request(url);
  network_manager->get(request);
}

void AddressInputDialog::onGeocodeFinished(QNetworkReply *reply) {
  if (reply->error() != QNetworkReply::NoError) {
    results_list->clear();
    results_list->addItem(tr("Error: Unable to search address"));
    results_list->show();
    reply->deleteLater();
    return;
  }

  QByteArray response_data = reply->readAll();
  QJsonDocument doc = QJsonDocument::fromJson(response_data);
  QJsonArray features = doc.object()["features"].toArray();

  displayResults(features);
  reply->deleteLater();
}

void AddressInputDialog::displayResults(const QJsonArray &features) {
  results.clear();
  results_list->clear();

  if (features.isEmpty()) {
    results_list->addItem(tr("No results found"));
    results_list->show();
    return;
  }

  for (const QJsonValue &feature : features) {
    QJsonObject obj = feature.toObject();
    QJsonArray coordinates = obj["center"].toArray();

    GeocodingResult result;
    result.display_name = obj["place_name"].toString();
    result.address = result.display_name;
    result.longitude = coordinates[0].toDouble();
    result.latitude = coordinates[1].toDouble();

    results.push_back(result);
    results_list->addItem(result.display_name);
  }

  results_list->show();
}

void AddressInputDialog::onResultSelected(QListWidgetItem *item) {
  int index = results_list->row(item);
  if (index >= 0 && index < static_cast<int>(results.size())) {
    selected_address = results[index].address;
    selected_lat = results[index].latitude;
    selected_lon = results[index].longitude;
    result_selected = true;
    accept();
  }
}

void AddressInputDialog::handleCancel() {
  result_selected = false;
  reject();
}
