import tkinter as tk
from tkinter import ttk, Text, Frame, Scrollbar, PanedWindow, Menu, filedialog, messagebox
import re
from datetime import datetime
import threading
import requests
import json
import os


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = ""

SYSTEM_PROMPT = (
    "You are EXCODER, an advanced AI coding agent with full filesystem capabilities. "
    "You have persistent memory of all created/modified files and can read entire project folders. "
    "Your core functions are:\n\n"
    "[create_file] path/filename.ext\n"
    "```python\n# Your code here\n```\n\n"
    "[edit_file] path/filename.ext\n"
    "```python\n# Modified code here\n```\n\n"
    "[analyze_file] path/filename.ext\n"
    "-> In this case, read the file’s full content and output an analysis of its design and possible improvements.\n\n"
    "Do not include any extra text before the file command line. After performing a file operation, confirm with "
    "\"File operation successful: ...\".\n\n"
    "This is an open-source AI coding agent. Awaiting task: What application shall we build or modify today?"
)

SYNTAX_PATTERNS = {
    "Python": [
        (r'#.*$', 'comment'),
        (r'""".*?"""', 'string'),
        (r"'''.*?'''", 'string'),
        (r'"[^"]*"', 'string'),
        (r"'[^']*'", 'string'),
        (r'\b(def|class|return|if|else|elif|for|while|import|from|as|try|except|finally|with|raise|and|or|not|in|is|None|True|False)\b', 'keyword'),
        (r'\b(?:self|cls)\b', 'self'),
        (r'\b(?:[0-9]+(?:\.[0-9]+)?)\b', 'number'),
    ],
    "JavaScript": [
        (r'//.*$', 'comment'),
        (r'/\*[\s\S]*?\*/', 'comment'),
        (r'"[^"]*"', 'string'),
        (r"'[^']*'", 'string'),
        (r'\b(function|return|if|else|for|while|var|let|const|import|from|export|class)\b', 'keyword'),
        (r'\b([0-9]+)\b', 'number'),
    ],
    "HTML": [
        (r'<!--[\s\S]*?-->', 'comment'),
        (r'<[^>]+>', 'tag'),
        (r'".*?"', 'string'),
        (r"'.*?'", 'string'),
    ],
    "CSS": [
        (r'/\*[\s\S]*?\*/', 'comment'),
        (r'\.[a-zA-Z0-9_-]+', 'class'),
        (r'\#[a-zA-Z0-9_-]+', 'id'),
        (r'\b(color|background|font-size|margin|padding)\b', 'property'),
    ],
    "C++": [
        (r'//.*$', 'comment'),
        (r'/\*[\s\S]*?\*/', 'comment'),
        (r'"[^"]*"', 'string'),
        (r"'[^']*'", 'string'),
        (r'\b(int|float|double|char|if|else|for|while|return|class|public|private)\b', 'keyword'),
    ],
    "Java": [
        (r'//.*$', 'comment'),
        (r'/\*[\s\S]*?\*/', 'comment'),
        (r'"[^"]*"', 'string'),
        (r"'[^']*'", 'string'),
        (r'\b(public|private|protected|class|interface|void|int|new|return|if|else|for|while)\b', 'keyword'),
    ],
    "Generic": [
        (r'".*?"', 'string'),
        (r"'.*?'", 'string'),
        (r'\b(if|else|for|while|return)\b', 'keyword'),
    ]
}


class SublimeStyleIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("EXCODER")
        self.root.geometry("1400x900")
        
        messagebox.showinfo("WARNING:", "Hi there, this is an opensource project, im hoping to see people get this further since im not capable sadly, but i would be really happy if i would see this project go further in. BROKENIST. PLEASE GO TO https://console.groq.com/ to get an api key, don't worry its free ")
        
        self.file_memory = {}
        self.current_file = None
        self.current_folder = None
        self.current_language = "Python"  # default
        self.current_model = "llama-3.3-70b-versatile"  # default model

        self.allow_changes_var = tk.BooleanVar(value=True)
        
        self.bg_color = "#000000"
        self.fg_color = "#d4d4d4"
        self.sidebar_bg = "#121212"
        self.line_num_bg = "#1a1a1a"
        self.line_num_fg = "#858585"
        self.highlight_color = "#333333"
        self.indent_guide_color = "#404040"
        self.chat_bg = "#121212"
        self.chat_fg = "#cccccc"
        
        self.main_pane = PanedWindow(root, orient=tk.HORIZONTAL, bg=self.bg_color)
        self.main_pane.pack(fill=tk.BOTH, expand=True)
        
        self.editor_frame = Frame(self.main_pane, bg=self.bg_color)
        self.main_pane.add(self.editor_frame)
        
        self.line_numbers = Text(self.editor_frame, width=4, padx=5, pady=5,
                                 bg=self.line_num_bg, fg=self.line_num_fg,
                                 insertbackground=self.fg_color, relief=tk.FLAT,
                                 font=('Consolas', 12), state=tk.NORMAL)
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        
        self.text = Text(self.editor_frame, bg=self.bg_color, fg=self.fg_color,
                         insertbackground=self.fg_color, relief=tk.FLAT,
                         selectbackground=self.highlight_color, wrap=tk.NONE,
                         font=('Consolas', 12), undo=True, state=tk.NORMAL)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.scrollbar = Scrollbar(self.editor_frame, command=self.sync_scroll)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.sidebar = Frame(self.main_pane, bg=self.sidebar_bg, width=300)
        self.main_pane.add(self.sidebar)
        
        self.create_chat_interface()
        self.create_file_explorer()
        
        self.status_bar = ttk.Label(root, text="Line: 1, Column: 1 | UTF-8 | Code", background=self.bg_color, foreground=self.fg_color)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.create_menu()
        
        self.configure_tags()
        
        self.text.bind("<KeyRelease>", self.on_text_change)
        self.text.bind("<Key>", self.on_key_press)
        self.text.config(yscrollcommand=self.scrollbar.set)
        self.text.bind("<Motion>", self.update_cursor_position)
        self.text.bind("<Button-1>", self.update_cursor_position)
        
        self.update_line_numbers()
        self.add_indent_guides()
        
        self.text.config(state=tk.NORMAL)
        
    def sync_scroll(self, *args):
        self.text.yview(*args)
        self.line_numbers.yview(*args)
    
    def create_chat_interface(self):
        # Main chat frame
        chat_frame = tk.Frame(self.sidebar, bg=self.chat_bg)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Chat history with scrollbar
        chat_history_frame = tk.Frame(chat_frame)
        chat_history_frame.pack(fill=tk.BOTH, expand=True)

        chat_scrollbar = tk.Scrollbar(chat_history_frame)
        chat_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.chat_history = tk.Text(
            chat_history_frame, 
            wrap=tk.WORD, 
            bg=self.chat_bg, 
            fg=self.chat_fg,
            font=('Arial', 10),
            yscrollcommand=chat_scrollbar.set,
            state='normal',  # Explicitly set to normal
            padx=10,
            pady=10
        )
        self.chat_history.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        chat_scrollbar.config(command=self.chat_history.yview)

        # Input frame
        input_frame = tk.Frame(chat_frame, bg=self.chat_bg)
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        # Input scrollbar
        input_scrollbar = tk.Scrollbar(input_frame)
        input_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Chat input
        self.chat_input = tk.Text(
            input_frame, 
            height=3, 
            wrap=tk.WORD, 
            bg=self.bg_color, 
            fg=self.fg_color,
            font=('Arial', 10),
            yscrollcommand=input_scrollbar.set,
            state='normal',  # Explicitly set to normal
            padx=5,
            pady=5
        )
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        input_scrollbar.config(command=self.chat_input.yview)

        # Send button
        send_button = tk.Button(
            input_frame, 
            text='Send', 
            command=self.send_chat_message,
            bg=self.highlight_color,
            fg=self.fg_color
        )
        send_button.pack(side=tk.RIGHT, padx=5)

        # Bind Enter key to send message
        self.chat_input.bind('<Return>', self.send_chat_message)

    def send_chat_message(self, event=None):
        # Get message from input
        message = self.chat_input.get("1.0", tk.END).strip()
        
        if message:
            # Clear input
            self.chat_input.delete("1.0", tk.END)
            
            # Add user message to chat history
            self.chat_history.insert(tk.END, f"You: {message}\n", 'user')
            self.chat_history.see(tk.END)
            
            # Process message
            if message.startswith("[create_file]") or message.startswith("[edit_file]") or message.startswith("[analyze_file]"):
                self.handle_chat_command(message)
            else:
                # Send to Groq API in a separate thread
                threading.Thread(target=self.send_to_groq_api, args=(message,), daemon=True).start()
        
        # Prevent default behavior
        return 'break'

    def append_chat(self, message):
        # Always ensure the chat history is in a normal state
        self.chat_history.config(state='normal')
        self.chat_history.insert(tk.END, f"{message}\n")
        self.chat_history.see(tk.END)
        self.chat_history.config(state='normal')  # Keep it normal

    def configure_tags(self):
        # Add tags for different message types
        self.chat_history.tag_config('user', foreground='lightblue')
        self.chat_history.tag_config('ai', foreground='lightgreen')
        self.chat_history.tag_config('system', foreground='lightgray', font=('Arial', 10, 'italic'))
        self.text.tag_config('comment', foreground="#6A9955")
        self.text.tag_config('string', foreground="#CE9178")
        self.text.tag_config('keyword', foreground="#569CD6")
        self.text.tag_config('self', foreground="#9CDCFE")
        self.text.tag_config('number', foreground="#B5CEA8")
        self.text.tag_config('tag', foreground="#569CD6")
        self.text.tag_config('class', foreground="#DCDCAA")
        self.text.tag_config('id', foreground="#4EC9B0")
        self.text.tag_config('property', foreground="#D4D4D4")
        self.text.tag_config('decorator', foreground="#9CDCFE")
        self.text.tag_config('builtin', foreground="#DCDCAA")
        self.text.tag_config('indent_guide', foreground=self.indent_guide_color)

    def create_file_explorer(self):
        explorer_frame = tk.Frame(self.sidebar, bg=self.sidebar_bg)
        explorer_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        title_frame = tk.Frame(explorer_frame, bg=self.sidebar_bg)
        title_frame.pack(fill=tk.X)
        
        lbl = ttk.Label(title_frame, text="File Explorer", background=self.sidebar_bg, foreground=self.fg_color)
        lbl.pack(side=tk.LEFT, anchor="w")
        
        btn_frame = tk.Frame(title_frame, bg=self.sidebar_bg)
        btn_frame.pack(side=tk.RIGHT)
        
        new_file_btn = ttk.Button(btn_frame, text="+", width=3, command=self.create_new_file)
        new_file_btn.pack(side=tk.LEFT, padx=2)
        
        refresh_btn = ttk.Button(btn_frame, text="🔄", width=3, command=self.refresh_file_list)
        refresh_btn.pack(side=tk.LEFT, padx=2)
        
        list_frame = tk.Frame(explorer_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.file_listbox = tk.Listbox(
            list_frame, 
            bg=self.bg_color, 
            fg=self.fg_color,
            selectbackground=self.highlight_color,
            selectforeground=self.fg_color,
            activestyle='none',
            font=('Consolas', 10),
            yscrollcommand=scrollbar.set
        )
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)
        
        self.file_listbox.bind("<Double-Button-1>", self.open_selected_file)
        
        self.file_context_menu = tk.Menu(self.file_listbox, tearoff=0)
        self.file_context_menu.add_command(label="Open", command=self.open_selected_file_from_menu)
        self.file_context_menu.add_command(label="Delete", command=self.delete_selected_file)
        self.file_listbox.bind("<Button-3>", self.show_file_context_menu)
    
    def create_new_file(self):
        untitled_count = len([f for f in self.file_memory.keys() if f.startswith('Untitled')]) + 1
        new_file_name = f'Untitled{untitled_count}.py'
        
        self.file_memory[new_file_name] = ''
        self.current_file = new_file_name
        
        self.text.delete('1.0', tk.END)
        self.text.focus_set()
        
        self.refresh_file_list()
        
        try:
            index = list(self.file_memory.keys()).index(new_file_name)
            self.file_listbox.selection_clear(0, tk.END)
            self.file_listbox.selection_set(index)
            self.file_listbox.activate(index)
        except ValueError:
            pass
        
        self.append_chat(f"Created new file: {new_file_name}")
    
    def refresh_file_list(self):
        self.file_listbox.delete(0, tk.END)
        
        all_files = list(self.file_memory.keys())
        
        if self.current_folder:
            try:
                folder_files = os.listdir(self.current_folder)
                all_files.extend([f for f in folder_files if os.path.isfile(os.path.join(self.current_folder, f)) and f not in all_files])
            except Exception as e:
                self.append_chat(f"Error reading folder: {e}")
        
        for f in all_files:
            self.file_listbox.insert(tk.END, f)
    
    def open_selected_file_from_menu(self):
        selection = self.file_listbox.curselection()
        if selection:
            self.open_selected_file(None)
    
    def delete_selected_file(self):
        selection = self.file_listbox.curselection()
        if selection:
            file_name = self.file_listbox.get(selection[0])
            
            if messagebox.askyesno("Delete File", f"Are you sure you want to delete {file_name}?"):
                try:
                    if file_name in self.file_memory:
                        del self.file_memory[file_name]
                    
                    if self.current_folder:
                        full_path = os.path.join(self.current_folder, file_name)
                        if os.path.exists(full_path):
                            os.remove(full_path)
                    
                    self.refresh_file_list()
                    
                    if self.current_file == file_name:
                        self.text.delete('1.0', tk.END)
                        self.current_file = None
                    
                    self.append_chat(f"Deleted file: {file_name}")
                except Exception as e:
                    messagebox.showerror("Error", f"Could not delete file: {e}")
    
    def show_file_context_menu(self, event):
        selection = self.file_listbox.nearest(event.y)
        self.file_listbox.selection_clear(0, tk.END)
        self.file_listbox.selection_set(selection)
        
        self.file_context_menu.tk_popup(event.x_root, event.y_root)
        self.file_context_menu.grab_release()
    
    def open_selected_file(self, event):
        selection = self.file_listbox.curselection()
        if selection and self.current_folder:
            file_name = self.file_listbox.get(selection[0])
            full_path = os.path.join(self.current_folder, file_name)
            self.open_file_in_editor(full_path)
    
    def open_file(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.current_folder = os.path.dirname(file_path)
            self.open_file_in_editor(file_path)
            self.refresh_file_list()
    
    def open_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.current_folder = folder
            self.append_chat(f"Opened folder: {folder}")
            self.refresh_file_list()
    
    def new_file(self):
        self.current_file = None
        self.text.delete("1.0", tk.END)
        self.append_chat("New file. You can now type your code.")
    
    def toggle_edit_mode(self):
        self.text.config(state=tk.NORMAL)
        self.chat_input.config(state=tk.NORMAL)
        self.chat_history.config(state=tk.NORMAL)
        self.append_chat("Editing always enabled.")
    
    def send_to_groq_api(self, user_message):
        extra_context = ""
        if self.current_folder:
            folder_context = "Folder code context:\n"
            try:
                for f in os.listdir(self.current_folder):
                    full_path = os.path.join(self.current_folder, f)
                    if os.path.isfile(full_path):
                        with open(full_path, "r", encoding="utf-8") as file:
                            file_content = file.read()
                        folder_context += f"--- {f} ---\n" + file_content + "\n\n"
                extra_context = folder_context
            except Exception as e:
                extra_context = "Error reading folder: " + str(e)
        payload = {
            "model": self.current_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": extra_context},
                {"role": "user", "content": user_message}
            ]
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}"
        }
        try:
            response = requests.post(GROQ_API_URL, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as e:
            content = f"Error calling groq API: {e}"
        self.root.after(0, self.display_response, content)
    
    def display_response(self, content):
        timestamp = datetime.now().strftime("%H:%M")
        self.chat_history.config(state='normal')
        self.chat_history.insert(tk.END, f"[{timestamp}] CodeSynth: {content}\n", 'ai')
        self.chat_history.config(state='normal')
        self.chat_history.see(tk.END)
        if "[create_file]" in content or "[edit_file]" in content or "[analyze_file]" in content:
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if line.startswith("[create_file]") or line.startswith("[edit_file]") or line.startswith("[analyze_file]"):
                    command_block = "\n".join(lines[i:])
                    self.handle_chat_command(command_block)
                    break
    
    def handle_chat_command(self, message):
        message = message.replace("```python", "").replace("```", "")
        lines = message.splitlines()
        if not lines:
            return
        command_line = lines[0]
        code_content = "\n".join(lines[1:]) if len(lines) > 1 else ""
        
        def animate_insertion(widget, text, idx=0):
            if idx < len(text):
                widget.insert(tk.END, text[idx])
                widget.see(tk.END)
                self.root.after(20, animate_insertion, widget, text, idx+1)
        
        if command_line.startswith("[create_file]"):
            file_name = command_line[len("[create_file]"):].strip()
            try:
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write("")
                self.file_memory[file_name] = ""
                self.append_chat(f"Created/overwritten file '{file_name}'.")
                self.current_file = file_name
                self.text.delete("1.0", tk.END)
                animate_insertion(self.text, code_content)
                threading.Thread(target=self.save_animated, args=(file_name, code_content)).start()
            except Exception as e:
                self.append_chat(f"Error creating file '{file_name}': {e}")
        
        elif command_line.startswith("[edit_file]"):
            file_name = command_line[len("[edit_file]"):].strip()
            try:
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write("")
                self.file_memory[file_name] = ""
                self.append_chat(f"Edited file '{file_name}'.")
                self.current_file = file_name
                self.text.delete("1.0", tk.END)
                animate_insertion(self.text, code_content)
                threading.Thread(target=self.save_animated, args=(file_name, code_content)).start()
            except Exception as e:
                self.append_chat(f"Error editing file '{file_name}': {e}")
        
        elif command_line.startswith("[analyze_file]"):
            file_name = command_line[len("[analyze_file]"):].strip()
            if os.path.exists(file_name):
                try:
                    with open(file_name, "r", encoding="utf-8") as f:
                        content = f.read()
                    analysis_message = f"Please analyze the following file and suggest improvements:\n{content}"
                    threading.Thread(target=self.send_to_groq_api, args=(analysis_message,)).start()
                    self.append_chat(f"Analyzing file '{file_name}'.")
                except Exception as e:
                    self.append_chat(f"Error reading file '{file_name}': {e}")
            else:
                self.append_chat(f"File '{file_name}' does not exist for analysis.")
    
    def save_animated(self, file_name, content):
        try:
            current_text = ""
            for char in content:
                current_text += char
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(current_text)
                threading.Event().wait(0.01)
            self.file_memory[file_name] = content
        except Exception as e:
            self.append_chat(f"Error during animated save for '{file_name}': {e}")
    
    def open_file_in_editor(self, file_path):
        self.current_file = file_path
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.text.delete("1.0", tk.END)
            def animate_file(text, idx=0):
                if idx < len(text):
                    self.text.insert(tk.END, text[idx])
                    self.text.see(tk.END)
                    self.root.after(10, animate_file, text, idx+1)
            animate_file(content)
            self.append_chat(f"Opened file '{file_path}' in editor.")
        except Exception as e:
            self.append_chat(f"Error opening file '{file_path}': {e}")
    
    def save_current_file(self):
        if self.current_file:
            content = self.text.get("1.0", tk.END)
            try:
                with open(self.current_file, "w", encoding="utf-8") as f:
                    f.write(content)
                self.file_memory[self.current_file] = content
                self.append_chat(f"Saved '{self.current_file}'.")
            except Exception as e:
                self.append_chat(f"Error saving file '{self.current_file}': {e}")
        else:
            messagebox.showerror("Error", "No file is currently open.")

    
    def on_key_press(self, event):
        if event.keysym == 'Tab':
            self.text.insert(tk.INSERT, ' ' * 4)
            return 'break'
        elif event.keysym == 'Return':
            self.auto_indent()
            return 'break'
    
    def auto_indent(self):
        current_line = self.text.get("insert linestart", "insert")
        leading_space = re.match(r'^ *', current_line).group()
        self.text.insert(tk.INSERT, '\n' + leading_space)
        if current_line.strip().endswith(':'):
            self.text.insert(tk.INSERT, ' ' * 4)
    
    def on_text_change(self, event=None):
        self.update_line_numbers()
        self.highlight_syntax()
        self.update_cursor_position()
        self.add_indent_guides()
        if event and event.keysym == 'colon':
            cursor_pos = self.text.index(tk.INSERT)
            line, col = cursor_pos.split('.')
            current_line = self.text.get(f"{line}.0", f"{line}.end")
            if current_line.endswith(':') and int(col) == len(current_line):
                stripped = current_line.strip()
                if stripped:
                    parts = stripped.split()
                    if parts[0] in ['if', 'elif', 'else', 'for', 'while', 'def', 'class']:
                        leading_space = re.match(r'^ *', current_line).group()
                        self.text.insert(tk.INSERT, '\n' + leading_space + ' ' * 4)
    
    def update_line_numbers(self):
        lines = self.text.get("1.0", tk.END).split('\n')
        line_numbers_text = '\n'.join(str(i) for i in range(1, len(lines)))
        self.line_numbers.config(state=tk.NORMAL)
        self.line_numbers.delete("1.0", tk.END)
        self.line_numbers.insert("1.0", line_numbers_text)
        self.line_numbers.config(state=tk.NORMAL)
    
    def highlight_syntax(self):
        for tag in self.text.tag_names():
            if tag != 'sel':
                self.text.tag_remove(tag, "1.0", tk.END)
        text = self.text.get("1.0", tk.END)
        patterns = SYNTAX_PATTERNS.get(self.current_language, SYNTAX_PATTERNS["Generic"])
        for pattern, tag_name, *group in patterns:
            for match in re.finditer(pattern, text, re.MULTILINE):
                start, end = match.span(group[0] if group else 0)
                self.text.tag_add(tag_name, f"1.0 + {start} chars", f"1.0 + {end} chars")
    
    def add_indent_guides(self):
        self.text.tag_remove('indent_guide', "1.0", tk.END)
        text = self.text.get("1.0", tk.END)
        for match in re.finditer(r'^( {4})+', text, re.MULTILINE):
            for i in range(4, match.end(), 4):
                self.text.tag_add('indent_guide', 
                                  f"{match.start()+1}.{i-1}", 
                                  f"{match.start()+1}.{i}")
    
    def update_cursor_position(self, event=None):
        cursor_pos = self.text.index(tk.INSERT)
        line, col = cursor_pos.split('.')
        self.status_bar.config(text=f"Line: {line}, Column: {int(col)+1} | {self.current_language} | Model: {self.current_model}")
    
    def create_menu(self):
        menubar = Menu(self.root)
        
        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self.create_new_file)
        file_menu.add_command(label="Open File", command=self.open_file)
        file_menu.add_command(label="Open Folder", command=self.open_folder)
        file_menu.add_command(label="Save", command=self.save_current_file)
        menubar.add_cascade(label="File", menu=file_menu)
        
        language_menu = Menu(menubar, tearoff=0)
        languages = ["Python", "JavaScript", "HTML", "CSS", "C++", "Java", "Generic"]
        for lang in languages:
            language_menu.add_command(label=lang, command=lambda l=lang: self.set_language(l))
        menubar.add_cascade(label="Language", menu=language_menu)
        
        model_menu = Menu(menubar, tearoff=0)
        models = ["llama-3.3-70b-versatile", "llama-3.2-11b-text-preview", "llama-3.1-8b-instant"]
        for model in models:
            model_menu.add_command(label=model, command=lambda m=model: self.set_model(m))
        menubar.add_cascade(label="Model", menu=model_menu)
        
        view_menu = Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(label="Allow Changes", variable=self.allow_changes_var, command=self.toggle_edit_mode)
        menubar.add_cascade(label="View", menu=view_menu)
        
        self.root.config(menu=menubar)
    
    def set_language(self, lang):
        self.current_language = lang
        self.append_chat(f"Language set to {lang}.")
        self.highlight_syntax()  
    
    def set_model(self, model):
        self.current_model = model
        self.append_chat(f"Model set to {model}.")
    
    def toggle_edit_mode(self):
        self.text.config(state=tk.NORMAL)
        self.chat_input.config(state=tk.NORMAL)
        self.chat_history.config(state=tk.NORMAL)
        self.append_chat("Editing always enabled.")


if __name__ == "__main__":
    root = tk.Tk()
    ide = SublimeStyleIDE(root)
    root.mainloop()
