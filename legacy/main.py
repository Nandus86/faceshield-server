import tkinter as tk
import config
from ui.menu_screen import MenuScreen
from ui.register_screen import RegisterScreen
from ui.recognition_screen import RecognitionScreen
from ui.logs_screen import LogsScreen
from ui.settings_screen import SettingsScreen
from ui.manage_screen import ManageScreen
from ui.analytics_screen import AnalyticsScreen

class FacialRecognitionApp:
    """Main application class."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Sistema de Reconhecimento Facial")
        self.root.geometry(f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}")
        self.root.configure(bg="#1e1e2e")
        
        # Center window
        self.center_window()
        
        # Initialize screens
        self.menu_screen = MenuScreen(
            self.root,
            on_recognize=self.show_recognition,
            on_register=self.show_register,
            on_view_logs=self.show_logs,
            on_settings=self.show_settings,
            on_manage=self.show_manage,
            on_analytics=self.show_analytics
        )
        
        self.register_screen = RegisterScreen(
            self.root,
            on_back=self.show_menu
        )
        
        self.recognition_screen = RecognitionScreen(
            self.root,
            on_back=self.show_menu
        )
        
        self.logs_screen = LogsScreen(
            self.root,
            on_back=self.show_menu
        )
        
        self.settings_screen = SettingsScreen(
            self.root,
            on_back=self.show_menu
        )
        
        self.manage_screen = ManageScreen(
            self.root,
            on_back=self.show_menu
        )
        
        self.analytics_screen = AnalyticsScreen(
            self.root,
            on_back=self.show_menu
        )
        
        # Start with menu
        self.current_screen = self.menu_screen
        self.current_screen.show()
    
    def center_window(self):
        """Center the window on screen."""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
    
    def switch_screen(self, new_screen):
        """Switch to a different screen."""
        self.current_screen.hide()
        self.current_screen = new_screen
        self.current_screen.show()
    
    def show_menu(self):
        """Show the menu screen."""
        self.switch_screen(self.menu_screen)
    
    def show_register(self):
        """Show the registration screen."""
        self.switch_screen(self.register_screen)
    
    def show_recognition(self):
        """Show the recognition screen."""
        self.switch_screen(self.recognition_screen)
    
    def show_logs(self):
        """Show the logs screen."""
        self.switch_screen(self.logs_screen)
    
    def show_settings(self):
        """Show the settings screen."""
        self.switch_screen(self.settings_screen)
    
    def show_manage(self):
        """Show the manage screen."""
        self.switch_screen(self.manage_screen)
    
    def show_analytics(self):
        """Show the analytics screen."""
        self.switch_screen(self.analytics_screen)
    
    def run(self):
        """Start the application."""
        self.root.mainloop()


if __name__ == "__main__":
    app = FacialRecognitionApp()
    app.run()
