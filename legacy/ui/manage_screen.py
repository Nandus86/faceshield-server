import tkinter as tk
from tkinter import font, messagebox, ttk
import os
from datetime import datetime
from PIL import Image, ImageTk
import cv2
from core.database import FaceDatabase

class ManageScreen:
    """Screen to manage registered people."""
    
    def __init__(self, root, on_back):
        self.root = root
        self.on_back = on_back
        self.database = FaceDatabase()
        
        self.frame = tk.Frame(root, bg="#1e1e2e")
        self.create_widgets()
    
    def create_widgets(self):
        """Create management UI elements."""
        # Title
        title_font = font.Font(family="Arial", size=24, weight="bold")
        title = tk.Label(
            self.frame,
            text="Gerenciar Cadastros",
            font=title_font,
            bg="#1e1e2e",
            fg="#cdd6f4"
        )
        title.pack(pady=20)
        
        # Info label
        self.info_label = tk.Label(
            self.frame,
            text="",
            font=("Arial", 12),
            bg="#1e1e2e",
            fg="#a6adc8"
        )
        self.info_label.pack(pady=5)
        
        # Main content frame
        content_frame = tk.Frame(self.frame, bg="#1e1e2e")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)
        
        # Create treeview for registered people
        tree_frame = tk.Frame(content_frame, bg="#1e1e2e")
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Treeview
        columns = ("Nome", "Data de Cadastro", "Fotos", "Primeira Foto")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            yscrollcommand=scrollbar.set,
            height=15
        )
        
        # Configure scrollbar
        scrollbar.config(command=self.tree.yview)
        
        # Define column headings
        self.tree.heading("Nome", text="Nome")
        self.tree.heading("Data de Cadastro", text="Data de Cadastro")
        self.tree.heading("Fotos", text="Nº Fotos")
        self.tree.heading("Primeira Foto", text="Primeira Foto")
        
        # Define column widths
        self.tree.column("Nome", width=150)
        self.tree.column("Data de Cadastro", width=180)
        self.tree.column("Fotos", width=80)
        self.tree.column("Primeira Foto", width=250)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Style treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Treeview",
            background="#181825",
            foreground="#cdd6f4",
            fieldbackground="#181825",
            borderwidth=0
        )
        style.configure("Treeview.Heading", background="#313244", foreground="#cdd6f4")
        style.map("Treeview", background=[("selected", "#89b4fa")])
        
        # Button frame
        button_frame = tk.Frame(self.frame, bg="#1e1e2e")
        button_frame.pack(pady=20)
        
        # Refresh button
        self.refresh_btn = tk.Button(
            button_frame,
            text="🔄 Atualizar Lista",
            command=self.load_registered,
            font=("Arial", 12, "bold"),
            bg="#89b4fa",
            fg="#1e1e2e",
            activebackground="#74c7ec",
            relief=tk.FLAT,
            width=18,
            height=2,
            cursor="hand2"
        )
        self.refresh_btn.grid(row=0, column=0, padx=10)
        
        # View photo button
        self.view_btn = tk.Button(
            button_frame,
            text="🖼️ Ver Foto",
            command=self.view_photo,
            font=("Arial", 12, "bold"),
            bg="#a6e3a1",
            fg="#1e1e2e",
            activebackground="#94e2d5",
            relief=tk.FLAT,
            width=18,
            height=2,
            cursor="hand2"
        )
        self.view_btn.grid(row=0, column=1, padx=10)
        
        # Delete button
        self.delete_btn = tk.Button(
            button_frame,
            text="🗑️ Excluir Cadastro",
            command=self.delete_person,
            font=("Arial", 12, "bold"),
            bg="#f38ba8",
            fg="#1e1e2e",
            activebackground="#eba0ac",
            relief=tk.FLAT,
            width=18,
            height=2,
            cursor="hand2"
        )
        self.delete_btn.grid(row=0, column=2, padx=10)
        
        # Back button
        self.back_btn = tk.Button(
            button_frame,
            text="🔙 Voltar ao Menu",
            command=self.on_back,
            font=("Arial", 12, "bold"),
            bg="#6c7086",
            fg="#cdd6f4",
            activebackground="#585b70",
            relief=tk.FLAT,
            width=18,
            height=2,
            cursor="hand2"
        )
        self.back_btn.grid(row=1, column=0, columnspan=3, pady=(10, 0))
    
    def load_registered(self):
        """Load and display all registered people."""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Reload database
        self.database.load()
        
        # Get all names (unique)
        names = self.database.get_all_names()
        
        if not names:
            self.info_label.config(text="Nenhuma pessoa cadastrada ainda")
            return
        
        self.info_label.config(text=f"Total de {len(names)} pessoa(s) cadastrada(s)")
        
        # Add to treeview
        for name in sorted(names):
            info = self.database.get_person_info(name)
            date = info.get("registered_date", "N/A")
            photo_count = info.get("photo_count", 1)
            photo_path = info.get("image_path", "N/A")
            
            # Get just the filename
            if photo_path != "N/A":
                photo_path = os.path.basename(photo_path)
            
            self.tree.insert("", tk.END, values=(name, date, photo_count, photo_path))
    
    def view_photo(self):
        """View the photo of the selected person."""
        selection = self.tree.selection()
        
        if not selection:
            messagebox.showwarning(
                "Nenhuma Seleção",
                "Por favor, selecione uma pessoa da lista."
            )
            return
        
        item = self.tree.item(selection[0])
        name = item["values"][0]
        
        # Get photo path
        info = self.database.get_person_info(name)
        photo_path = info.get("image_path")
        
        if not photo_path or not os.path.exists(photo_path):
            messagebox.showerror(
                "Foto Não Encontrada",
                f"A foto de '{name}' não foi encontrada."
            )
            return
        
        # Create a new window to display the photo
        photo_window = tk.Toplevel(self.root)
        photo_window.title(f"Foto - {name}")
        photo_window.configure(bg="#1e1e2e")
        
        # Load and display image
        img = cv2.imread(photo_path)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_resized = cv2.resize(img_rgb, (400, 300))
        
        photo = ImageTk.PhotoImage(image=Image.fromarray(img_resized))
        
        label = tk.Label(photo_window, image=photo, bg="#1e1e2e")
        label.image = photo  # Keep a reference
        label.pack(padx=20, pady=20)
        
        # Close button
        close_btn = tk.Button(
            photo_window,
            text="Fechar",
            command=photo_window.destroy,
            font=("Arial", 12, "bold"),
            bg="#6c7086",
            fg="#cdd6f4",
            relief=tk.FLAT,
            width=15,
            cursor="hand2"
        )
        close_btn.pack(pady=(0, 20))
    
    def delete_person(self):
        """Delete the selected person."""
        selection = self.tree.selection()
        
        if not selection:
            messagebox.showwarning(
                "Nenhuma Seleção",
                "Por favor, selecione uma pessoa da lista."
            )
            return
        
        item = self.tree.item(selection[0])
        name = item["values"][0]
        
        # Confirm deletion
        confirm = messagebox.askyesno(
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir o cadastro de '{name}'?\n"
            "Esta ação não pode ser desfeita."
        )
        
        if not confirm:
            return
        
        try:
            success = self.database.delete_person(name)
            if success:
                messagebox.showinfo(
                    "Cadastro Excluído",
                    f"O cadastro de '{name}' foi excluído com sucesso."
                )
            else:
                messagebox.showwarning(
                    "Aviso",
                    f"Cadastro de '{name}' não encontrado."
                )
            
            # Refresh list
            self.load_registered()
            
        except Exception as e:
            messagebox.showerror(
                "Erro ao Excluir",
                f"Não foi possível excluir o cadastro:\n{e}"
            )
                "Erro ao Excluir",
                f"Não foi possível excluir o cadastro:\n{e}"
            )
    
    def show(self):
        """Display this screen."""
        self.frame.pack(fill=tk.BOTH, expand=True)
        self.load_registered()
    
    def hide(self):
        """Hide this screen."""
        self.frame.pack_forget()
