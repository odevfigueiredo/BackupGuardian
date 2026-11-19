<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:111827,100:2563EB&height=190&section=header&text=Backup%20Guardian&fontSize=48&fontColor=ffffff&animation=fadeIn&fontAlignY=35&desc=Seus%20arquivos%20protegidos%2C%20mesmo%20offline&descAlignY=58&descSize=17" alt="Backup Guardian" />

<div align="center">
  <p><strong>Backups verificáveis, restauração segura e criptografia de arquivos para Windows e Linux.</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Status-Em_desenvolvimento-2563EB?style=for-the-badge" alt="Status: em desenvolvimento" />
    <img src="https://img.shields.io/badge/Vers%C3%A3o-0.2-1D4ED8?style=for-the-badge" alt="Versão 0.2" />
    <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10 ou superior" />
    <img src="https://img.shields.io/badge/Windows%20%7C%20Linux-111827?style=for-the-badge" alt="Windows e Linux" />
    <img src="https://img.shields.io/badge/Funciona-Offline-334155?style=for-the-badge" alt="Funciona offline" />
  </p>
</div>

---

## 🛡️ Sobre

**Backup Guardian** é uma ferramenta de backup e recuperação de arquivos com interface gráfica e linha de comando. Permite criar cópias de pastas, verificar a integridade do conteúdo e restaurar arquivos a partir de snapshots, sem depender de serviços em nuvem.

O projeto é compatível com **Windows e Linux**, incluindo ambientes Linux no **Raspberry Pi**. Depois de preparar as dependências, pode ser utilizado sem conexão com a internet.

---

## ✨ Funcionalidades

- Criação de **snapshots** de pastas com cópias dos arquivos e manifesto de integridade.
- Verificação por **SHA-256** para identificar arquivos alterados, ausentes ou inesperados.
- Restauração com validação prévia e proteção contra substituição de destinos existentes.
- Preservação de **pastas vazias** nos snapshots criados a partir da versão 0.2.
- Leitura de snapshots da versão 0.1, respeitando os limites de dados registrados naquela versão.
- Criptografia e descriptografia de arquivos com senha usando os comandos `seal` e `unseal`.
- Interface gráfica com **Tkinter** e acesso por terminal.
- Operação offline após a instalação das dependências necessárias.
- Integração com o **Survival Server** para proteger arquivos de backup exportados pelo servidor.

---

## 🧱 Tecnologias

<div align="center">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Tkinter-1D4ED8?style=for-the-badge" alt="Tkinter" />
  <img src="https://img.shields.io/badge/SHA--256-475569?style=for-the-badge" alt="SHA-256" />
  <img src="https://img.shields.io/badge/AES--256--GCM-1E40AF?style=for-the-badge" alt="AES-256-GCM" />
  <img src="https://img.shields.io/badge/scrypt-334155?style=for-the-badge" alt="scrypt" />
  <img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" alt="GitHub Actions" />
</div>

---

## 🗂️ Arquivos principais

```text
BackupGuardian/
├── .github/
│   └── workflows/
│       └── python-ci.yml          # Adicione o workflow de testes
├── tests/                         # Testes automatizados
├── backup_guardian.py             # Ferramenta de linha de comando
├── guardian_gui.py                # Interface gráfica
├── iniciar_windows.bat            # Inicialização no Windows
├── iniciar_linux.sh               # Inicialização no Linux
├── requirements-crypto.txt        # Dependência de criptografia
└── README.md
```

> O diretório `.github/workflows/` é opcional e deve ser adicionado ao configurar os testes no GitHub Actions.

---

## 🚀 Como começar

### 1. Requisitos

- **Python 3.10 ou superior**.
- **Tkinter** para utilizar a interface gráfica (pode exigir instalação separada no Linux).
- Biblioteca **`cryptography`** para os comandos `seal` e `unseal`.

### 2. Obtenha o projeto

Clone o repositório pelo Git ou baixe seu conteúdo como ZIP no GitHub.

```bash
git clone https://github.com/odevfigueiredo/BackupGuardian.git
cd BackupGuardian
```

### 3. Abra a interface gráfica

**Windows:** execute `iniciar_windows.bat`.

**Linux / Raspberry Pi:**

```bash
sh iniciar_linux.sh
```

Se estiver usando um ambiente virtual com a dependência de criptografia instalada, você também pode iniciar a interface diretamente:

```bash
python guardian_gui.py
```

> Nos comandos, substitua `python` por `python3` (Linux) ou `py -3` (Windows) se necessário.

---

## 💾 Criar e recuperar backups

**Crie um snapshot:**

```bash
python backup_guardian.py create "./Meus Documentos" "E:/Copias"
```

**Liste os backups disponíveis:**

```bash
python backup_guardian.py list "E:/Copias"
```

**Verifique a integridade de um snapshot:**

```bash
python backup_guardian.py verify "E:/Copias/snapshots/ID_DO_BACKUP"
```

**Restaure o snapshot:**

```bash
python backup_guardian.py restore "E:/Copias/snapshots/ID_DO_BACKUP" "./Documentos Recuperados"
```

Substitua os caminhos pelos diretórios do seu computador e use o identificador retornado pelos comandos `create` ou `list`. **Escolha um destino que ainda não exista** para a restauração.

Cada snapshot contém uma cópia dos dados e um manifesto com hashes SHA-256. A verificação detecta diferenças em relação a esse manifesto. Novos snapshots exigem nomes de arquivos portáveis entre Windows e Linux.

---

## 🔐 Criptografia e privacidade

Os comandos `seal` e `unseal` permitem proteger arquivos com senha. A criptografia utiliza **AES-256-GCM** e derivação de chave com **scrypt**, no formato `BGUARD1`.

**Criptografe um arquivo:**

```bash
python backup_guardian.py seal "arquivo.zip" "arquivo.zip.bgc"
```

**Recupere o arquivo:**

```bash
python backup_guardian.py unseal "arquivo.zip.bgc" "arquivo-recuperado.zip"
```

A senha deve ter **pelo menos 12 caracteres**. Na recuperação, a autenticidade do arquivo é verificada antes de publicar o conteúdo descriptografado.

> **Importante:** snapshots comuns **não são criptografados automaticamente**. Para proteger um snapshot completo, compacte a pasta do snapshot em um ZIP e depois aplique `seal`. Mantenha a senha em local seguro: a perda da senha pode impedir a recuperação dos dados.

### Preparar a criptografia para uso offline

Em um computador com internet e ambiente compatível com o computador de destino, baixe os pacotes necessários:

```bash
python -m pip download --only-binary=:all: -r requirements-crypto.txt -d pacotes
```

Transfira a pasta `pacotes` e o projeto para a máquina offline. Na pasta do Backup Guardian, instale a dependência sem acessar a internet:

```bash
python -m pip install --no-index --find-links ./pacotes -r requirements-crypto.txt
```

---

## 🔄 Integração com o Survival Server

O Backup Guardian também pode criptografar backups gerados pelo Survival Server.

**1.** Na pasta do Survival Server, gere uma cópia consistente do banco de dados e arquivos:

```bash
python server.py backup "../BackupGuardian/backup-survival.zip"
```

**2.** Na pasta do Backup Guardian, criptografe o ZIP:

```bash
python backup_guardian.py seal "backup-survival.zip" "E:/Copias/backup-survival.zip.bgc"
```

**3.** Para recuperar, descriptografe o arquivo:

```bash
python backup_guardian.py unseal "E:/Copias/backup-survival.zip.bgc" "backup-restaurado.zip"
```

**4.** Pare o Survival Server e, na pasta dele, restaure o backup:

```bash
python server.py restore "../BackupGuardian/backup-restaurado.zip" --yes
```

Ajuste os caminhos de acordo com a localização dos dois projetos.

---

## 🧪 Testes e qualidade

Execute a suíte de testes na raiz do projeto:

```bash
python -m unittest discover -s tests -v
```

O workflow de integração contínua `python-ci.yml`, disponível separadamente, executa os testes em ambientes Windows e Linux com versões selecionadas do Python. Ele não gera um instalador: a aplicação é executada pelos scripts incluídos no repositório.

---

## 📌 Boas práticas de backup

- Adote a **regra 3-2-1**: três cópias, em dois tipos de mídia, com uma cópia em outro local.
- Verifique seus snapshots periodicamente e **teste a restauração** antes de depender dos backups.
- Preserve arquivos sensíveis em formato criptografado ao armazená-los em dispositivos externos.
- Evite copiar arquivos que estão sendo modificados. Para o Survival Server, utilize o comando próprio de backup.
- Guarde senhas e chaves de recuperação separadamente dos dispositivos de armazenamento.

---

## 🧭 Próximos passos

- Ampliar os testes de restauração e compatibilidade entre sistemas operacionais.
- Melhorar a experiência da interface gráfica e as mensagens de diagnóstico.
- Expandir a documentação de recuperação em situações de emergência.
- Avaliar mecanismos adicionais de automação e agendamento de backups.

---

<div align="center">
  <p>Desenvolvido por <a href="https://github.com/odevfigueiredo">Jonatha Figueiredo</a></p>
  <img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:2563EB,100:111827&height=120&section=footer" alt="" />
</div>
