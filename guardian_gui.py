#!/usr/bin/env python3
"""Interface local do Backup Guardian."""

from queue import Empty, SimpleQueue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import backup_guardian as g


class BackupGuardianApp:
    def __init__(self, root):
        self.root = root
        self.busy = False
        root.title('Backup Guardian • Offline')
        root.geometry('640x410')
        root.minsize(400, 380)
        root.protocol('WM_DELETE_WINDOW', self.close)

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Backup Guardian', font=('TkDefaultFont', 20, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Backups locais com verificação SHA-256').pack(anchor='w', pady=(4, 16))

        self.buttons = []
        for title, command in (
            ('Criar backup de pasta', self.create),
            ('Verificar integridade do backup', self.verify),
            ('Restaurar para nova pasta', self.restore),
            ('Criptografar arquivo', self.seal),
            ('Descriptografar arquivo', self.unseal),
        ):
            button = ttk.Button(frame, text=title, command=command)
            button.pack(fill='x', pady=4)
            self.buttons.append(button)

        self.status = tk.StringVar(master=root, value='Pronto para operar offline.')
        ttk.Label(frame, textvariable=self.status).pack(anchor='w', pady=(16, 0))

    def close(self):
        if self.busy:
            self.root.bell()
            return
        self.root.destroy()

    def _set_busy(self, busy):
        self.busy = busy
        for button in self.buttons:
            button.state(['disabled'] if busy else ['!disabled'])

    def _show_result(self, title, detail, *, ok=True):
        self.status.set(title)
        dialog = messagebox.showinfo if ok else messagebox.showerror
        dialog(title, detail, parent=self.root)

    def _run(self, progress, operation, show_result):
        if self.busy:
            return
        self._set_busy(True)
        self.status.set(progress)
        results = SimpleQueue()

        def job():
            try:
                results.put((True, operation()))
            except Exception as error:
                results.put((False, str(error) or type(error).__name__))

        def poll():
            try:
                ok, result = results.get_nowait()
            except Empty:
                self.root.after(75, poll)
                return
            self._set_busy(False)
            if ok:
                show_result(result)
            else:
                self._show_result('Falha na operação', result, ok=False)

        try:
            threading.Thread(target=job).start()
        except RuntimeError as error:
            self._set_busy(False)
            self._show_result('Falha ao iniciar a operação', str(error), ok=False)
            return
        self.root.after(75, poll)

    def _show_snapshot(self, title, result):
        path, count = result
        self._show_result(title, f'{count} arquivo(s) em\n{path}')

    def create(self):
        source = filedialog.askdirectory(title='Selecionar pasta de origem', parent=self.root)
        if not source:
            return
        vault = filedialog.askdirectory(title='Selecionar pasta para guardar os backups', parent=self.root)
        if vault:
            self._run('Criando backup…', lambda: g.create(source, vault),
                      lambda result: self._show_snapshot('Backup criado', result))

    def verify(self):
        snapshot = filedialog.askdirectory(title='Selecionar snapshot para verificar', parent=self.root)
        if snapshot:
            self._run('Verificando backup…', lambda: g.verify(snapshot), self._show_verification)

    def _show_verification(self, report):
        if report['ok']:
            self._show_result('Backup íntegro', f'{report["files"]} arquivo(s) conferido(s) com SHA-256.')
            return
        problems = report['problems']
        lines = [f'{len(problems)} problema(s) encontrado(s).', '', *problems[:8]]
        if len(problems) > 8:
            lines.append(f'… e mais {len(problems) - 8} problema(s).')
        self._show_result('Backup com falhas', '\n'.join(lines), ok=False)

    def restore(self):
        snapshot = filedialog.askdirectory(title='Selecionar snapshot para restaurar', parent=self.root)
        if not snapshot:
            return
        destination = filedialog.asksaveasfilename(title='Escolher o nome da nova pasta restaurada', parent=self.root)
        if destination:
            self._run('Restaurando backup…', lambda: g.restore(snapshot, destination),
                      lambda result: self._show_snapshot('Backup restaurado', result))

    def seal(self):
        source = filedialog.askopenfilename(title='Escolher arquivo para criptografar', parent=self.root)
        if not source:
            return
        destination = filedialog.asksaveasfilename(title='Salvar arquivo criptografado', defaultextension='.bgc',
                                                   filetypes=[('Backup Guardian', '*.bgc')], parent=self.root)
        if not destination:
            return
        password = simpledialog.askstring('Senha', 'Crie uma senha com pelo menos 12 caracteres.',
                                          show='*', parent=self.root)
        if password is None:
            return
        if len(password) < 12:
            self._show_result('Senha muito curta', 'Use pelo menos 12 caracteres.', ok=False)
            return
        confirmation = simpledialog.askstring('Confirmação da senha', 'Digite a senha novamente.',
                                              show='*', parent=self.root)
        if confirmation is None:
            return
        if password != confirmation:
            self._show_result('Senhas diferentes', 'Digite a mesma senha nos dois campos.', ok=False)
            return
        self._run('Criptografando arquivo…', lambda: g.seal_file(source, destination, password),
                  lambda path: self._show_result('Arquivo criptografado', str(path)))

    def unseal(self):
        source = filedialog.askopenfilename(title='Escolher arquivo criptografado', parent=self.root,
                                            filetypes=[('Backup Guardian', '*.bgc'), ('Todos os arquivos', '*')])
        if not source:
            return
        destination = filedialog.asksaveasfilename(title='Salvar arquivo descriptografado', parent=self.root)
        if not destination:
            return
        password = simpledialog.askstring('Senha', 'Digite a senha do arquivo.', show='*', parent=self.root)
        if password:
            self._run('Descriptografando arquivo…', lambda: g.unseal_file(source, destination, password),
                      lambda path: self._show_result('Arquivo descriptografado', str(path)))


def main():
    root = tk.Tk()
    BackupGuardianApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
