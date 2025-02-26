import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5 as Cipher_pkcs1_v1_5
from base64 import b64decode
import os
import pickle
import logging
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class UbookDownloader:
    def __init__(self, cookies_file="ubook_cookies.pkl"):
        self.base_url = "https://www.ubook.com"
        self.login_url = urljoin(self.base_url, "/login")
        self.favorites_url = urljoin(self.base_url, "/minhaConta/favoritos")
        self.session = requests.Session()
        self.driver = None
        self.cookies_file = cookies_file
        self.chrome_options = Options()
        self.chrome_options.add_argument("--disable-gpu")
        self.chrome_options.add_argument("--window-size=1920x1080")

    def load_cookies(self):
        """Carrega os cookies do arquivo."""
        try:
            with open(self.cookies_file, 'rb') as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    self.session.cookies.set(
                        cookie['name'], cookie['value'],
                        domain=cookie['domain'],
                        path=cookie.get('path', '/'),
                        secure=cookie.get('secure', False),
                        expires=cookie.get('expiry', None)
                    )
            logging.info("Cookies carregados com sucesso.")
            return True
        except FileNotFoundError:
            logging.warning("Arquivo de cookies não encontrado.")
            return False
        except EOFError:
            logging.warning("Arquivo de cookies vazio.")
            return False
        except pickle.UnpicklingError:
            logging.error("Erro ao desserializar os cookies (arquivo corrompido?).")
            return False
        except Exception as e:
            logging.error(f"Erro inesperado ao carregar cookies: {type(e).__name__} - {e}")
            return False

    def save_cookies(self, cookies):
        """Salva os cookies em um arquivo."""
        try:
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(cookies, f)
            logging.info("Cookies salvos com sucesso.")
        except Exception as e:
            logging.error(f"Erro ao salvar os cookies: {e}")

    def is_logged_in(self):
        """Verifica se o usuário está logado."""
        try:
            response = self.session.get(self.favorites_url)
            response.raise_for_status()
            if "minhaConta/favoritos" in response.url and "Minha Lista" in response.text:
                return True
            return False
        except requests.exceptions.RequestException as e:
            logging.warning(f"Erro ao acessar favoritos para verificar o login: {e}")
            return False
        except Exception as e:
            logging.error(f"Erro inesperado ao verificar o login: {e}")
            return False

    def login(self):
        """Realiza o login no Ubook, utilizando cookies ou login manual com WebDriver."""
        logging.info("Iniciando processo de login...")
        if self.load_cookies() and self.is_logged_in():
            logging.info("Login com cookies OK.")
            return
        logging.info("Cookies inválidos ou inexistentes. Iniciando login manual...")
        self.manual_login()

    def manual_login(self):
        """Realiza o login manual utilizando o Selenium WebDriver."""
        service = ChromeService(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=self.chrome_options)
        self.driver.get(self.login_url)
        try:
            logging.info("Faça login no Ubook (você pode usar email/senha, Google ou Facebook).")
            logging.info("O script continuará automaticamente quando você estiver na página 'Minha Lista'.")
            def wait_for_favorites_page(driver):
                try:
                    return "minhaConta/favoritos" in driver.current_url and driver.find_element(By.XPATH, "//a[contains(@href, '/minhaConta/favoritos')]")
                except (NoSuchElementException, WebDriverException):
                    return False
            WebDriverWait(self.driver, 3600).until(wait_for_favorites_page)
            logging.info("Login OK.")
            self.save_cookies(self.driver.get_cookies())
        except TimeoutException:
            raise Exception("Tempo limite excedido durante o login.")
        except Exception as e:
            raise Exception(f"Erro durante o login: {e}")
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None

    def get_favorites(self):
        """Obtém a lista de favoritos usando requests."""
        logging.info("Obtendo a lista de favoritos...")
        try:
            response = self.session.get(self.favorites_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            favorites = []
            for item in soup.select(".ProductList > div"):
                link = item.select_one("a.title")
                if link:
                    url = urljoin(self.base_url, link['href'])
                    title = link.text.strip()
                    favorites.append({"url": url, "title": title})
            logging.info(f"Encontrados {len(favorites)} favoritos.")
            return favorites
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao obter favoritos: {e}")
            return []
        except Exception as e:
            logging.error(f"Erro inesperado ao obter favoritos: {e}")
            return []

    def get_audiobook_info(self, book_url):
        """Obtém informações do audiolivro usando requests."""
        logging.info(f"Obtendo informações do audiobook: {book_url}")
        try:
            response = self.session.get(book_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            title = soup.select_one("h1.title").text.strip() if soup.select_one("h1.title") else "No title"
            print(f"Título: {title}")
            book_id = book_url.split('/')[-2]
            return {"id": book_id, "title": title}
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao obter informações do audiobook: {e}")
            return None
        except Exception as e:
            logging.error(f"Erro inesperado ao obter informações do audiobook: {e}")
            return None

    def get_chapter_urls(self, book_id):
        """Obtém os URLs dos capítulos usando requests, extraindo chaves do HTML."""
        book_url = f"{self.base_url}/audiobook/{book_id}"
        logging.info(f"Obtendo URLs dos capítulos para o audiobook: {book_url}")
        try:
            response = self.session.get(book_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')

            # Extrair chaves publicKey e privateKey do HTML
            script_tags = soup.find_all('script')
            public_key = None
            private_key = None
            for script in script_tags:
                if script.string and 'publicKey' in script.string:
                    match_public = re.search(r'publicKey:\s*"([^"]+)"', script.string)
                    match_private = re.search(r'privateKey:\s*"([^"]+)"', script.string)
                    if match_public:
                        public_key = match_public.group(1)
                    if match_private:
                        private_key = match_private.group(1)
                    break

            if not public_key or not private_key:
                raise Exception("Não foi possível encontrar as chaves publicKey e privateKey no HTML.")

            logging.info(f"Chave pública obtida: {public_key[:50]}...")
            logging.info(f"Chave privada obtida: {private_key[:50]}...")

            # Extrair informações dos capítulos
            chapters = []
            for i, chapter_el in enumerate(soup.select("#ubook_player_chapters_list li")):
                chapter_title = chapter_el.select_one("p.ubook_player_default_li_title a").text.strip()
                duration_str = chapter_el.select_one("p.ubook_player_default_li_desc a").text.replace("duração", "").strip()
                onclick_attr = chapter_el.select_one("p.ubook_player_default_li_title a")["onclick"]
                chapter_number = int(onclick_attr.split("(")[1].split(")")[0])
                chapters.append({"number": chapter_number, "title": chapter_title, "duration": duration_str, "url": None})
                print(f"Capítulo: {chapter_title}, Duração: {duration_str}, Número capítulo: {chapter_number}")

            # Obter URLs dos capítulos via requisição AJAX
            for i, chapter in enumerate(chapters):
                chapter_id = chapter['number']
                ajax_url = f"{self.base_url}/playerExternal/GetUrlFile"
                print(f"Tentando comunicação com: {ajax_url}")
                response = self.session.post(ajax_url, data={"catalog_id": book_id, "chapter_id": chapter_id, "publicKey": public_key})
                response.raise_for_status()
                print(f"Resposta da requisição: {response.text}")
                decrypted_response = self.decrypt_data(response.text, private_key)
                print(f"Resposta descriptografada: {decrypted_response}")

                if decrypted_response:
                    json_data = json.loads(decrypted_response)
                    if json_data.get("success"):
                        file_url = json_data["data"]["file_url"]
                        chapters[i]["url"] = file_url
                        print(f"URL do Capítulo {chapter['number']}: {file_url}")
                    else:
                        print(f"Erro ao obter URL do capítulo {chapter['number']}")
                else:
                    print(f"Erro ao obter URL do capítulo {chapter['number']} - Decriptação falhou")

            return chapters
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao obter lista de capítulos: {e}")
            return []
        except Exception as e:
            logging.error(f"Erro inesperado ao obter lista de capítulos: {e}")
            return []

    def decrypt_data(self, encrypted_data, private_key):
        """Descriptografa os dados usando a chave privada."""
        try:
            keyDER = b64decode(private_key)
            private_key = RSA.import_key(keyDER)
            cipher = Cipher_pkcs1_v1_5.new(private_key)
            decoded_string = b64decode(encrypted_data)
            decrypted_data = cipher.decrypt(decoded_string, "ERRO")
            return decrypted_data.decode('utf-8')
        except Exception as e:
            logging.error(f"Erro ao descriptografar dados: {e}")
            return None

    def download_chapter(self, chapter_url, chapter_title):
        """Implementar o download do MP3 aqui."""
        # TODO: Implementar o download do MP3
        pass

    def download_audiobook(self, book_url):
        """Baixa o audiolivro."""
        print(f"Baixando audiobook de: {book_url}")
        book_info = self.get_audiobook_info(book_url)
        if book_info:
            chapter_urls = self.get_chapter_urls(book_info["id"])
            if chapter_urls:
                print("Baixando os capítulos")
            else:
                print("Não foi possível baixar os capítulos")
        else:
            print("Não foi possível obter as informações do audiolivro")

if __name__ == "__main__":
    downloader = UbookDownloader()
    try:
        downloader.login()  # Usa WebDriver apenas aqui para login e cookies
        favorites = downloader.get_favorites()  # Usa requests
        if favorites:
            for fav in favorites:
                if "/audiobook/" in fav["url"]:
                    downloader.download_audiobook(fav["url"])  # Usa requests
                    break  # Para após o primeiro audiolivro
        else:
            print("Nenhum favorito encontrado.")
    finally:
        if downloader.driver:
            downloader.driver.quit()