# Installer Python avec pyenv

## Pourquoi

La VM Debian de production tourne sous **Python 3.11.2**. Les Mac et PC de
développement livrent aujourd'hui Python 3.13 ou 3.14, qui **ne peuvent pas** faire
tourner le bot : `discord.py` 2.4.0 importe `audioop`, retiré de Python 3.13 (PEP 594).

pyenv permet d'installer et de basculer entre plusieurs versions de Python sans toucher
au Python du système. Le fichier `.python-version` à la racine du dépôt contient `3.11.2`
et pyenv le lit automatiquement dès qu'on entre dans le dossier.

Plage supportée : **Python 3.10 à 3.12**. Version de référence : **3.11.2**.

## Debian / Ubuntu (la VM)

### 1. Dépendances de compilation

pyenv compile Python depuis les sources : sans ces paquets, la compilation réussit mais
produit un Python amputé (pas de `ssl`, pas de `sqlite3`, pas de `lzma`), et le bot
échoue plus tard avec des erreurs incompréhensibles.

```bash
sudo apt update
sudo apt install -y make build-essential libssl-dev zlib1g-dev libbz2-dev \
  libreadline-dev libsqlite3-dev wget curl llvm libncursesw5-dev xz-utils \
  tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev git
```

### 2. Installer pyenv

```bash
curl -fsSL https://pyenv.run | bash
```

### 3. Activer pyenv dans le shell

Ajouter à la fin de `~/.bashrc` :

```bash
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"
```

Puis recharger : `exec "$SHELL"`.

## macOS

```bash
brew install pyenv
```

Ajouter à la fin de `~/.zshrc` :

```bash
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - zsh)"
```

Puis recharger : `exec "$SHELL"`.

## Windows

pyenv ne fonctionne pas nativement sous Windows. Utiliser
[pyenv-win](https://github.com/pyenv-win/pyenv-win) :

```powershell
Invoke-WebRequest -UseBasicParsing -Uri https://raw.githubusercontent.com/pyenv-win/pyenv-win/master/pyenv-win/install-pyenv-win.ps1 -OutFile "./install-pyenv-win.ps1"; &"./install-pyenv-win.ps1"
```

Le bot lui-même se lance sous Windows, mais les workers SeleniumBase de `scripts/`
supposent un affichage Unix (`pyvirtualdisplay`) et ne fonctionneront pas tels quels.

## Installer la version du projet

Depuis la racine du dépôt :

```bash
pyenv install 3.11.2
```

`.python-version` étant déjà versionné, pyenv sélectionne 3.11.2 automatiquement dès
qu'on entre dans le dossier. Vérifier :

```bash
python -V     # doit afficher Python 3.11.2
```

Si ce n'est pas le cas, l'initialisation du shell (étape 3) n'a pas été prise en compte.

## Créer l'environnement virtuel

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Vérifier

L'installation n'est pas terminée tant que la suite de tests n'est pas verte :

```bash
pytest
```

Résultat attendu : `18 passed`.

## Note sur uv

`uv` est une alternative plus rapide à `venv` + `pip`, mais **ne publie pas Python
3.11.2** (sa liste passe de 3.11.1 à 3.11.3). Un `uv venv` sans argument lit
`.python-version`, cherche 3.11.2 et échoue. Il faut donc préciser la version mineure :

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
```

Cela installe un 3.11.x récent, pas 3.11.2 exactement. Pour reproduire la production à
l'identique, utiliser pyenv.
