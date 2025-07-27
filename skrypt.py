import os
import json
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget,
                            QVBoxLayout, QLabel, QLineEdit, QPushButton,
                            QMessageBox, QStackedWidget, QTextEdit, QHBoxLayout,
                            QSpinBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Konfiguracja
APP_VERSION = "1.6.3"
WEBAPP_URL = "https://www.ea.com/pl-pl/ea-sports-fc/ultimate-team/web-app/"
os.makedirs('auth', exist_ok=True)
os.makedirs('data', exist_ok=True)

USERS_FILE = 'auth/users.json'
TOKEN_FILE = 'data/token.txt'

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
                            price = items[0].find_element(By.CSS_SELECTOR, ".currency-coins").text
                            
                            # 3. Natychmiastowe kupowanie
                            items[0].click()
                            
                            WebDriverWait(self.driver, 0.1).until(
                                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'buyButton')]"))
                            ).click()
                            
                            WebDriverWait(self.driver, 0.1).until(
                                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Ok')]"))
                            ).click()
                            
                            self.found_signal.emit(f"⚡ Karta zakupiona: {player_name} za {price}")
                            time.sleep(5)  # Dodane opóźnienie między wyszukiwaniami
                            continue
                            
                    except (TimeoutException, NoSuchElementException):
                        pass
                    
                    # 4. Powrót do wyszukiwania
                    try:
                        WebDriverWait(self.driver, 0.1).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, "ut-navigation-button-control"))
                        ).click()
                    except:
                        pass
                    
                    time.sleep(5)  # Dodane opóźnienie między wyszukiwaniami
                    
                except Exception as e:
                    if not self.force_stop:
                        self.error_signal.emit(f"⚠️ Błąd: {str(e)}")
                    time.sleep(5)  # Dodane opóźnienie po błędzie
                    
        except Exception as e:
            self.error_signal.emit(f"❌ Błąd: {str(e)}")
        finally:
            self.running = False

    def stop(self):
        self.force_stop = True
        self.running = False

class AuthManager:
    @staticmethod
    def load_users():
        if not os.path.exists(USERS_FILE):
            return {}
        try:
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}

    @staticmethod
    def register(username, password):
        if not username.strip() or not password.strip():
            return False, "Login i hasło nie mogą być puste"
            
        users = AuthManager.load_users()
        if username in users:
            return False, "Użytkownik już istnieje"
        
        users[username] = {'password': password}
        try:
            with open(USERS_FILE, 'w') as f:
                json.dump(users, f, indent=4)
            return True, "Rejestracja udana!"
        except Exception as e:
            return False, f"Błąd zapisu: {str(e)}"

    @staticmethod
    def login(username, password):
        users = AuthManager.load_users()
        if not users:
            return False, "Brak zarejestrowanych użytkowników"
            
        if username not in users:
            return False, "Nieprawidłowy login"
            
        if users[username]['password'] != password:
            return False, "Nieprawidłowe hasło"
            
        return True, "Zalogowano pomyślnie!"

class LoginWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("EA FC 25 Ultra Snipe")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Login")
        self.username_input.setStyleSheet("padding: 8px;")
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Hasło")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet("padding: 8px;")
        
        self.login_btn = QPushButton("Zaloguj")
        self.login_btn.setStyleSheet("padding: 8px; background-color: #4CAF50; color: white;")
        self.login_btn.clicked.connect(self.handle_login)
        
        self.register_btn = QPushButton("Zarejestruj")
        self.register_btn.setStyleSheet("padding: 8px;")
        self.register_btn.clicked.connect(self.handle_register)

        layout.addWidget(title)
        layout.addSpacing(20)
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_input)
        layout.addSpacing(10)
        layout.addWidget(self.login_btn)
        layout.addWidget(self.register_btn)
        
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

    def handle_register(self):
        username = self.username_input.text()
        password = self.password_input.text()
        
        success, message = AuthManager.register(username, password)
        if success:
            QMessageBox.information(self, "Sukces", message)
        else:
            QMessageBox.warning(self, "Błąd", message)

class MainApp(QWidget):
    def __init__(self):
        super().__init__()
        self.token_fetcher = None
        self.snipe_bot = None
        self.driver = None
        self.init_ui()

    def init_ui(self):
        self.tabs = QTabWidget()
        
        # Zakładka UltraSnipe
        self.tab1 = QWidget()
        tab1_layout = QVBoxLayout()
        
        header = QLabel("⚡ Ultra Snipe Bot")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        tab1_layout.addWidget(header)
        
        self.start_btn = QPushButton("START")
        self.start_btn.setStyleSheet("""
            QPushButton {
                padding: 10px;
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.start_btn.clicked.connect(self.start_snipe)
        
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                padding: 10px;
                background-color: #f44336;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_snipe)
        self.stop_btn.setEnabled(False)
        
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("background: #f8f8f8; padding: 10px;")
        
        tab1_layout.addWidget(self.start_btn)
        tab1_layout.addWidget(self.stop_btn)
        tab1_layout.addWidget(QLabel("Log działania:"))
        tab1_layout.addWidget(self.log)
        
        self.tab1.setLayout(tab1_layout)
        
        # Zakładka Token
        self.tab2 = QWidget()
        tab2_layout = QVBoxLayout()
        
        self.token_btn = QPushButton("Pobierz Token")
        self.token_btn.setStyleSheet("""
            QPushButton {
                padding: 10px;
                background-color: #2196F3;
                color: white;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.token_btn.clicked.connect(self.get_token)
        
        self.token_status = QLabel("Status: Nie zalogowano")
        tab2_layout.addWidget(self.token_status)
        tab2_layout.addWidget(self.token_btn)
        
        self.tab2.setLayout(tab2_layout)
        
        self.tabs.addTab(self.tab1, "UltraSnipe")
        self.tabs.addTab(self.tab2, "Token")
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

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
        self.log.append(f"[{time.strftime('%H:%M:%S')}] 🚀 ULTRA SNIPE AKTYWNY")

    def stop_snipe(self):
        if self.snipe_bot:
            self.snipe_bot.stop()
            self.snipe_bot = None
            
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log.append(f"[{time.strftime('%H:%M:%S')}] 🛑 ZATRZYMANO")

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
        self.log.append(f"[{time.strftime('%H:%M:%S')}] ✅ Token gotowy")

    def update_log(self, message):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {message}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"EA FC 25 Ultra Snipe {APP_VERSION}")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
        """)
        
        self.stack = QStackedWidget()
        
        self.login_window = LoginWindow(self)
        self.main_app = MainApp()
        
        self.stack.addWidget(self.login_window)
        self.stack.addWidget(self.main_app)
        
        self.setCentralWidget(self.stack)
        self.show_login()

    def show_login(self):
        self.stack.setCurrentIndex(0)

    def show_main_app(self):
        self.stack.setCurrentIndex(1)

if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()