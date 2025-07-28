import sys
import os
import json
import time
import requests
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTextEdit, QStackedWidget, QLineEdit, 
    QMessageBox, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QFile, QTextStream, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Konfiguracja
APP_VERSION = "0.5 BETA"
WEBAPP_URL = "https://www.ea.com/pl-pl/ea-sports-fc/ultimate-team/web-app/"
os.makedirs('data', exist_ok=True)

USERS_FILE = 'auth/users.json'
TOKEN_FILE = 'data/token.txt'
WEBHOOK_FILE = 'data/webhook.txt'
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # lub twoje hasło
    'database': 'ultrasnipe'  # nazwa bazy danych
}

class TokenFetcher(QThread):
    update_signal = pyqtSignal(str)
    token_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.driver = None
        self.running = False

    def run(self):
        try:
            options = Options()
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1200,800")
            options.add_argument("--disable-notifications")
            
            self.update_signal.emit("🔄 Uruchamianie przeglądarki Chrome...")
            self.driver = webdriver.Chrome(options=options)
            
            self.update_signal.emit(f"🌐 Otwieranie: {WEBAPP_URL}")
            self.driver.get(WEBAPP_URL)
            
            self.update_signal.emit("🔑 Proszę zalogować się ręcznie w przeglądarce...")
            self.update_signal.emit("🕒 Masz 5 minut na zalogowanie się")
            self.running = True
            
            start_time = time.time()
            while self.running and (time.time() - start_time) < 300:
                try:
                    token = self.driver.execute_script(
                        "return window.localStorage.getItem('_eadp.identity.access_token');"
                    )
                    
                    if token:
                        with open(TOKEN_FILE, 'w') as f:
                            f.write(token)                        
                        self.token_signal.emit(token)
                        self.running = False
                        break
                    
                    time.sleep(3)
                    
                except Exception as e:
                    self.error_signal.emit(f"⚠️ Błąd: {str(e)}")
                    time.sleep(3)
            
            if time.time() - start_time >= 300:
                raise TimeoutError("Przekroczono czas oczekiwania na logowanie")
            
        except Exception as e:
            self.error_signal.emit(f"❌ Błąd: {str(e)}")
        finally:
            self.running = False

    def stop(self):
        self.running = False
        return self.driver

class UltraSnipeBot(QThread):
    update_signal = pyqtSignal(str)
    found_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, driver=None):
        super().__init__()
        self.driver = driver
        self.running = False
        self.force_stop = False

    def run(self):
        try:
            if not self.driver:
                raise Exception("Brak połączenia z przeglądarką")
                
            if not os.path.exists(TOKEN_FILE):
                raise Exception("Nie znaleziono tokenu")
                
            with open(TOKEN_FILE, 'r') as f:
                token = f.read().strip()
                
            if not token:
                raise Exception("Token jest pusty")
            
            self.running = True
            search_count = 0
            
            while self.running and not self.force_stop:
                search_count += 1
                self.update_signal.emit(f"🔍 Wyszukiwanie #{search_count}...")
                
                try:
                    # 1. Kliknij Search
                    WebDriverWait(self.driver, 0.5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Search')]"))
                    ).click()
                    
                    # 2. Szybkie sprawdzenie wyników
                    try:
                        items = WebDriverWait(self.driver, 0.1).until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".listFUTItem"))
                        )
                        
                        if items:
                            # Pobierz nazwę i cenę karty
                            player_name = items[0].find_element(By.CSS_SELECTOR, ".name").text
                            player_price = items[0].find_element(By.CSS_SELECTOR, ".currency-coins").text
                            
                            # 3. Natychmiastowe kupowanie
                            items[0].click()
                            
                            WebDriverWait(self.driver, 0.1).until(
                                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'buyButton')]"))
                            ).click()
                            
                            WebDriverWait(self.driver, 0.1).until(
                                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Ok')]"))
                            ).click()
                            
                            self.found_signal.emit(f"⚡ Zakupiono: {player_name} za {player_price}")
                            self.send_webhook_notification(player_name, player_price)
                            
                            # Dodana przerwa po zakupie
                            self.update_signal.emit("⏸️ Przerwa po zakupie - 30 sekund...")
                            for i in range(30, 0, -1):
                                if self.force_stop:
                                    break
                                time.sleep(1)
                                if i % 5 == 0:
                                    self.update_signal.emit(f"⏳ Pozostało {i} sekund...")
                            
                            if not self.force_stop:
                                self.update_signal.emit("▶️ Wznawianie wyszukiwania...")
                            
                            # Powrót do wyszukiwania
                            self.go_back_to_search()
                            continue
                            
                    except (TimeoutException, NoSuchElementException):
                        self.go_back_to_search()
                    
                    time.sleep(5)
                    
                except Exception as e:
                    if not self.force_stop:
                        self.error_signal.emit(f"⚠️ Błąd: {str(e)}")
                    time.sleep(5)
                    
        except Exception as e:
            self.error_signal.emit(f"❌ Błąd: {str(e)}")
        finally:
            self.running = False

    def go_back_to_search(self):
        try:
            WebDriverWait(self.driver, 0.1).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "ut-navigation-button-control"))
            ).click()
        except:
            pass

    def send_webhook_notification(self, player_name, player_price):
        """Wysyła powiadomienie na Discord przez Webhook"""
        if not os.path.exists(WEBHOOK_FILE):
            return

        with open(WEBHOOK_FILE, 'r') as f:
            webhook_url = f.read().strip()

        if not webhook_url:
            return

        try:
            payload = {
                "embeds": [{
                    "title": "Udało ci się kupić Karte!",
                    "description": f"**Karta:** {player_name}",
                    "color": 16711770,
                    "footer": {
                        "text": f"FutRush"
                    }
                }]
            }
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception as e:
            self.error_signal.emit(f"⚠️ Błąd webhooka: {str(e)}")

    def stop(self):
        self.force_stop = True
        self.running = False

class AuthManager:
    @staticmethod
    def get_connection():
        return mysql.connector.connect(**DB_CONFIG)

    @staticmethod
    def login(username, password):
        conn = None
        try:
            conn = AuthManager.get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()

            if not user:
                return False, "Nieprawidłowy login"

            if user['password'] != password:
                return False, "Nieprawidłowe hasło"

            expiry_date = user['expires_at']
            if datetime.now().date() > expiry_date:
                return False, f"Licencja wygasła ({expiry_date})"

            return True, "Zalogowano pomyślnie!"

        except Error as e:
            return False, f"Błąd bazy danych: {str(e)}"
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

class LoginWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        self.setObjectName("login-window")
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        logo = QLabel()
        logo.setObjectName("login-logo")
        logo.setPixmap(QPixmap("logo.png").scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Login")
        self.username_input.setObjectName("login-input")
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Hasło")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setObjectName("login-input")
        
        self.login_btn = QPushButton("Zaloguj")
        self.login_btn.setObjectName("login-btn")
        self.login_btn.clicked.connect(self.handle_login)
        

        layout.addWidget(logo)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_btn)
        
        self.setLayout(layout)

    def handle_login(self):
        username = self.username_input.text()
        password = self.password_input.text()
        
        success, message = AuthManager.login(username, password)
        if success:
            QMessageBox.information(self, "Sukces", message)
            self.parent.show_main_app()
        else:
            QMessageBox.warning(self, "Błąd", message)

class MainApp(QWidget):
    def __init__(self, username="Użytkownik"):
        super().__init__()
        self.username = username
        self.token_fetcher = None
        self.snipe_bot = None
        self.driver = None
        self.init_ui()

    def init_ui(self):
        self.setObjectName("main-app")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Sidebar
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        logo = QLabel()
        logo.setPixmap(QPixmap("logo.png").scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo)

        self.btn_sniper = QPushButton("🎯")
        self.btn_token = QPushButton("🔐")
        self.btn_settings = QPushButton("⚙")

        for i, btn in enumerate([self.btn_sniper, self.btn_token, self.btn_settings]):
            btn.setObjectName("sidebar-btn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, index=i: self.switch_page(index))
            sidebar_layout.addWidget(btn)

        spacer = QWidget()
        spacer.setObjectName("sidebar-spacer")
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(), spacer.sizePolicy().Expanding)

        logout_btn = QPushButton("⟲")
        logout_btn.setObjectName("logout-btn")
        logout_btn.clicked.connect(self.logout)

        sidebar_layout.addWidget(spacer)
        sidebar_layout.addWidget(logout_btn)

        self.sidebar.setLayout(sidebar_layout)

        # Main Panel
        self.pages = QStackedWidget()
        self.pages.setObjectName("main-panel")

        self.sniper_page = self.create_sniper_page()
        self.token_page = self.create_token_page()
        self.settings_page = self.create_settings_page()

        self.pages.addWidget(self.sniper_page)
        self.pages.addWidget(self.token_page)
        self.pages.addWidget(self.settings_page)

        layout.addWidget(self.sidebar)
        layout.addWidget(self.pages)

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)

    def create_sniper_page(self):
        page = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

    # Lewa kolumna z przyciskami wyśrodkowanymi pionowo
        controls_widget = QWidget()
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(10)

    # Dodaj "rozciągacze" dla wyśrodkowania
        controls_layout.addStretch()

        self.start_btn = QPushButton("START SNIPER")
        self.start_btn.setObjectName("start-btn")
        self.start_btn.clicked.connect(self.start_snipe)

        self.stop_btn = QPushButton("STOP SNIPER")
        self.stop_btn.setObjectName("stop-btn")
        self.stop_btn.clicked.connect(self.stop_snipe)
        self.stop_btn.setEnabled(False)

        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.stop_btn)

        controls_layout.addStretch()

        
        controls_widget.setLayout(controls_layout)

    # Prawa kolumna z logami
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setObjectName("log-text")

        # Dodanie do głównego layoutu
        layout.addWidget(controls_widget, 1)
        layout.addWidget(self.log_text, 3)

        page.setLayout(layout)
        return page

    def create_token_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)

        self.token_status = QLabel("Status: Nie zalogowano")
        self.token_status.setObjectName("token-status")
        self.token_status.setProperty("class", "token-error")

        self.token_btn = QPushButton("Pobierz Token")
        self.token_btn.setObjectName("token-btn")
        self.token_btn.clicked.connect(self.get_token)

        layout.addWidget(self.token_status)
        layout.addWidget(self.token_btn)
        page.setLayout(layout)
        return page

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Version info
        version_label = QLabel(f"Wersja: {APP_VERSION}")
        version_label.setObjectName("version-label")
        version_label.setAlignment(Qt.AlignCenter)
        
        # Webhook section
        webhook_label = QLabel("Discord Webhook URL:")
        webhook_label.setAlignment(Qt.AlignCenter)
        self.webhook_input = QLineEdit()
        self.webhook_input.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.webhook_input.setObjectName("webhook-input")
        
        # Load saved webhook if exists
        if os.path.exists(WEBHOOK_FILE):
            with open(WEBHOOK_FILE, 'r') as f:
                self.webhook_input.setText(f.read().strip())
        
        save_webhook_btn = QPushButton("Zapisz Webhook")
        save_webhook_btn.setObjectName("save-webhook-btn")
        save_webhook_btn.clicked.connect(self.save_webhook)
        
        # Update check section
        check_update_btn = QPushButton("Sprawdź aktualizacje")
        check_update_btn.setObjectName("check-update-btn")
        check_update_btn.clicked.connect(self.check_for_updates)
        
        self.update_status = QLabel("")
        self.update_status.setObjectName("update-status")
        self.update_status.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(version_label)
        layout.addStretch(1)
        layout.addWidget(webhook_label)
        layout.addWidget(self.webhook_input)
        layout.addWidget(save_webhook_btn)
        layout.addStretch(1)
        layout.addWidget(check_update_btn)
        layout.addWidget(self.update_status)
        layout.addStretch(2)
        
        page.setLayout(layout)
        return page

    def save_webhook(self):
        webhook_url = self.webhook_input.text().strip()
        if webhook_url:
            os.makedirs('data', exist_ok=True)
            with open(WEBHOOK_FILE, 'w') as f:
                f.write(webhook_url)
            QMessageBox.information(self, "Sukces", "Webhook został zapisany!")
        else:
            QMessageBox.warning(self, "Błąd", "URL webhooka nie może być pusty")

    def check_for_updates(self):
        try:
            version_url = "https://raw.githubusercontent.com/yourusername/yourrepo/main/version.txt"
            response = requests.get(version_url)
            response.raise_for_status()
            
            latest_version = response.text.strip()
            if latest_version > APP_VERSION:
                self.update_status.setText(f"Dostępna nowa wersja: {latest_version}")
                self.update_status.setProperty("class", "update-available")
                QMessageBox.information(self, "Aktualizacja", 
                                      f"Dostępna jest nowa wersja {latest_version}!\n\n"
                                      f"Twoja wersja: {APP_VERSION}")
            else:
                self.update_status.setText("Masz najnowszą wersję")
                self.update_status.setProperty("class", "update-current")
                QMessageBox.information(self, "Aktualizacja", "Masz najnowszą wersję aplikacji")
                
            self.update_status.setStyleSheet("")
        except Exception as e:
            self.update_status.setText("Błąd sprawdzania aktualizacji")
            self.update_status.setProperty("class", "update-error")
            self.update_status.setStyleSheet("")
            QMessageBox.warning(self, "Błąd", f"Nie udało się sprawdzić aktualizacji:\n{str(e)}")

    def start_snipe(self):
        if self.snipe_bot and self.snipe_bot.isRunning():
            return
        driver = self.token_fetcher.driver if self.token_fetcher else None
        self.snipe_bot = UltraSnipeBot(driver)
        self.snipe_bot.update_signal.connect(self.update_log)
        self.snipe_bot.found_signal.connect(self.update_log)
        self.snipe_bot.error_signal.connect(self.update_log)
        self.snipe_bot.start()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.update_log(f"[{time.strftime('%H:%M:%S')}] 🚀 ULTRA SNIPE AKTYWNY")

    def stop_snipe(self):
        if self.snipe_bot:
            self.snipe_bot.stop()
            self.snipe_bot = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.update_log(f"[{time.strftime('%H:%M:%S')}] 🛑 ZATRZYMANO")

    def get_token(self):
        if self.token_fetcher and self.token_fetcher.isRunning():
            return

        self.token_fetcher = TokenFetcher()
        self.token_fetcher.update_signal.connect(self.update_log)
        self.token_fetcher.token_signal.connect(self.token_obtained)
        self.token_fetcher.error_signal.connect(self.update_log)
        self.token_fetcher.start()

    def token_obtained(self, token):
        self.token_status.setText("Status: Zalogowano")
        self.token_status.setProperty("class", "token-success")
        self.token_status.setStyleSheet("")
        self.update_log(f"[{time.strftime('%H:%M:%S')}] ✅ Token gotowy")

    def update_log(self, message):
        self.log_text.append(message)

    def logout(self):
        parent_window = self.parent()
        while parent_window and not isinstance(parent_window, QMainWindow):
            parent_window = parent_window.parent()
        if parent_window:
            parent_window.show_login()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("logo.ico"))
        self.setWindowTitle(f"FutRush")
        self.setFixedSize(880, 540)

        self.stack = QStackedWidget()

        self.login_window = LoginWindow(self)
        self.main_app = None

        self.stack.addWidget(self.login_window)
        self.setCentralWidget(self.stack)
        self.show_login()
        self.load_stylesheet()

    def show_login(self):
        self.stack.setCurrentIndex(0)

    def show_main_app(self):
        username = self.login_window.username_input.text()
        self.main_app = MainApp(username)
        self.stack.addWidget(self.main_app)
        self.stack.setCurrentWidget(self.main_app)

    def load_stylesheet(self):
        style_file = QFile("style.css")
        if style_file.open(QFile.ReadOnly | QFile.Text):
            stream = QTextStream(style_file)
            self.setStyleSheet(stream.readAll())
            style_file.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())