from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Header, Footer, TabbedContent, TabPane, Input, Button, ListView, ListItem, Label
from textual.message import Message
from textual.widget import Widget

import asyncio
import shlex
import re

# Regex zum Entfernen von ANSI-Escape-Codes aus Strings
_ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def remove_ansi_escape_codes(text: str) -> str:
    """Entfernt ANSI-Escape-Codes (z.B. Farb- oder Formatierungscodes) aus einem String."""
    return _ansi_escape.sub('', text)

# ---
# Eine benutzerdefinierte ListItem-Klasse fÃ¼r selektierbare Pakete
# ---

class SelectablePackageListItem(ListItem):
    """
    Ein benutzerdefiniertes ListItem, das den Auswahlstatus eines Pakets verfolgt
    und visuelles Feedback bei Klick gibt.
    """
    def __init__(self, package_name: str, **kwargs):
        super().__init__(Label(package_name), **kwargs)
        self.package_name = package_name
        self.selected = False # Interner Zustand fÃ¼r die Auswahl

    class Toggled(Message):
        """
        Eine Textual-Nachricht, die gesendet wird, wenn der Auswahlstatus
        eines SelectablePackageListItem geÃ¤ndert wird.
        """
        def __init__(self, item: "SelectablePackageListItem", selected: bool) -> None:
            super().__init__()
            self.item = item
            self.selected = selected

    def on_click(self) -> None:
        """
        Wird aufgerufen, wenn auf dieses ListItem geklickt wird.
        Schaltet den Auswahlstatus um und sendet eine Toggled-Nachricht.
        """
        self.selected = not self.selected
        if self.selected:
            self.add_class("-selected") # CSS-Klasse fÃ¼r ausgewÃ¤hltes Aussehen
        else:
            self.remove_class("-selected")
        # Sende die Nachricht an die App, damit sie den Auswahlstatus verfolgen kann
        self.post_message(self.Toggled(self, self.selected))

# ---
# Haupt-App-Klasse
# ---

class MyApp(App):

    # Der Pfad zu deiner CSS-Datei. Stelle sicher, dass sie im selben Verzeichnis ist.
    CSS_PATH = "main.css"

    # Tastenkombinationen fÃ¼r globale Aktionen
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
    ]

    # Ein Set zum Speichern der Namen der aktuell ausgewÃ¤hlten Pakete.
    selected_packages: set[str] = set()

    def compose(self) -> ComposeResult:
        """
        Erstellt die Widgets fÃ¼r die BenutzeroberflÃ¤che der Anwendung.
        """
        yield Header() # Der obere Bereich der App

        # Haupt-TabbedContent-Komponente fÃ¼r die Navigation zwischen den Ansichten
        with TabbedContent(id="main_tabs"):
            # Erster Tab: "Download"
            with TabPane("Download", id="tab-download"):
                with Container(id="download_tab"):
                    with VerticalScroll(id="download_area"):
                        yield Label("Search and Download Packages", id="download_title")

                        # Suchleiste mit Eingabefeld und "Search"-Button
                        with Container(id="search_bar"):
                            self.search_input = Input(placeholder="Enter package keywords...", id="search_input")
                            yield self.search_input
                            self.search_button = Button("Search", id="search_button", variant="primary")
                            yield self.search_button

                        # ListView fÃ¼r die Anzeige der Suchergebnisse
                        self.packages_list = ListView(id="packages_list")
                        yield self.packages_list

                        # "Download Selected Package"-Button
                        self.download_button = Button("Download Selected Packages", id="download_button", variant="success")
                        yield self.download_button

            # Zweiter Tab: "Compile" (Platzhalter)
            with TabPane("Compile", id="tab-compile"):
                yield Label("Compile tab content will go here.")

            # Dritter Tab: "Export" (Platzhalter)
            with TabPane("Export", id="tab-export"):
                yield Label("Export tab content will go here.")

        yield Footer() # Der untere Bereich der App

    # ---
    # Event Handling fÃ¼r Buttons
    # ---

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """
        Wird aufgerufen, wenn ein Button in der App gedrÃ¼ckt wird.
        Leitet den Klick je nach Button-ID an die entsprechende Funktion weiter.
        """
        if event.button.id == "search_button":
            await self.run_apt_search()
        elif event.button.id == "download_button":
            await self.run_apt_source_download() # GeÃ¤ndert auf apt source

    def on_selectable_package_list_item_toggled(self, message: SelectablePackageListItem.Toggled) -> None:
        """
        Wird aufgerufen, wenn ein SelectablePackageListItem (Paket in der Liste)
        angeklickt und sein Auswahlstatus geÃ¤ndert wird.
        Aktualisiert das 'selected_packages'-Set der App.
        """
        package_name = message.item.package_name
        if message.selected:
            self.selected_packages.add(package_name)
            self.notify(f"'{package_name}' selected.", timeout=1, severity="information")
        else:
            self.selected_packages.discard(package_name)
            self.notify(f"'{package_name}' deselected.", timeout=1, severity="information")

        self.download_button.label = f"Download Selected ({len(self.selected_packages)}) Packages"

    # ---
    # FunktionalitÃ¤t fÃ¼r APT-Suche
    # ---

    async def run_apt_search(self) -> None:
        """
        FÃ¼hrt den 'apt search'-Befehl basierend auf den Keywords im Input-Feld aus
        und zeigt die gefundenen Paketnamen in der ListView an.
        """
        keywords = self.search_input.value.strip()

        if not keywords:
            self.notify("Please enter search keywords.", severity="warning")
            return

        self.notify(f"Searching for '{keywords}'...", timeout=3)
        self.packages_list.clear()
        self.selected_packages.clear()
        self.download_button.label = "Download Selected Packages"

        command = shlex.split(f"apt search {keywords}")

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_message_raw = stderr.decode().strip()
                error_message = remove_ansi_escape_codes(error_message_raw)
                self.notify(f"Error during APT search: {error_message or 'Unknown error'}", severity="error")
                return

            output = stdout.decode().strip()

            if not output:
                self.packages_list.append(ListItem(Label("No packages found.")))
                self.notify("No packages found.", severity="info")
                return

            package_name_pattern = re.compile(r"^([^/]+)/")
            found_packages_count = 0

            for line in output.split('\n'):
                match = package_name_pattern.match(line)
                if match:
                    package_name = match.group(1).strip()
                    if package_name:
                        self.packages_list.append(SelectablePackageListItem(package_name))
                        found_packages_count += 1

            if found_packages_count == 0:
                 self.packages_list.append(ListItem(Label("No relevant packages found after parsing.")))
                 self.notify("No relevant packages found after parsing the output.", severity="info")
            else:
                 self.notify(f"Search complete. Found {found_packages_count} packages.", severity="success")

        except FileNotFoundError:
            self.notify("Error: 'apt' command not found. Is APT installed and in your PATH?", severity="error")
        except Exception as e:
            self.notify(f"An unexpected error occurred: {e}", severity="error")

    # ---
    # FunktionalitÃ¤t fÃ¼r APT Source Code Download
    # ---

    async def run_apt_source_download(self) -> None:
        """
        LÃ¤dt den Quellcode der ausgewÃ¤hlten Pakete mit 'apt source' herunter.
        Dieser Befehl ist architekturunabhÃ¤ngig.
        """
        if not self.selected_packages:
            self.notify("No packages selected for source code download.", severity="warning")
            return

        self.notify(f"Starting source code download for {len(self.selected_packages)} packages...", timeout=5)

        for package_name in list(self.selected_packages):
            self.notify(f"Downloading source code for '{package_name}'...", timeout=2)

            # Befehl zum Herunterladen des Quellcodes
            command = shlex.split(f"apt-get source --download-only {package_name}")
            
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_message_raw = stderr.decode().strip()
                    error_message = remove_ansi_escape_codes(error_message_raw)
                    self.notify(f"Failed to download source for '{package_name}': {error_message or 'Unknown error'}", severity="error")
                else:
                    self.notify(f"Successfully downloaded source for '{package_name}'.", severity="success")
                    self.selected_packages.discard(package_name)

            except FileNotFoundError:
                self.notify("Error: 'apt' command not found. Cannot perform source download.", severity="error")
                break
            except Exception as e:
                self.notify(f"An unexpected error occurred during source download of '{package_name}': {e}", severity="error")

        self.download_button.label = f"Download Selected ({len(self.selected_packages)}) Packages"
        if not self.selected_packages:
            self.notify("All selected packages attempted source download.", severity="info")
            self.download_button.label = "Download Selected Packages"

    # ---
    # Aktionen fÃ¼r Tastenkombinationen (BINDINGS)
    # ---

    def action_toggle_dark(self) -> None:
        """Eine Aktion zum Umschalten des Dark-Modus der Anwendung."""
        self.dark = not self.dark

    def action_quit(self) -> None:
        """Eine Aktion zum Beenden der Anwendung."""
        self.exit()

# Startpunkt der Anwendung
if __name__ == "__main__":
    app = MyApp()
    app.run()