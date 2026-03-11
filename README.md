# Hackathon Nsigma x Neovision 2026 — NeoRando 

## Equipes Demolastre: Noah Deplace , Antoine Marion, Nolan Blanc

Template de projet pour le hackathon. Consultez d'abord le [SUJET](SUJET.md) pour les consignes complètes (contexte, contraintes, évaluation).

## Installation

### GitHub

Avant toute chose :

1. Créez un repo GitHub **privé** pour ce projet.
2. Ajoutez `lorisfloquet` comme collaborateur (`Settings → Collaborators → Add people`) ainsi que tous les membres de votre équipe. C'est la personne qui se chargera d'évaluer votre solution.

> Le repo doit rester privé jusqu'à la fin du hackathon, ensuite libre à vous d'en faire ce que vous voulez.

### VSCode

Si votre IDE est VSCode, nous vous conseillons d'installer ces [extensions](.vscode/extensions.json) (normalement VSCode va vous les proposer gentiment).

> NB : Si l'extension Ruff râle, pas de panique, allez à la section suivante et une fois le venv créé l'extension ne râlera plus (vous pouvez restart les extensions ou VSCode si le changement n'est pas actif immédiatement).

Par ailleurs, au cas où votre version de VSCode serait trop ancienne, nous vous rappelons que la meilleure façon d'installer VSCode sur **vos machines** avec **Ubuntu** est la [suivante](https://code.visualstudio.com/docs/setup/linux) :

```bash
sudo apt-get install wget gpg
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -D -o root -g root -m 644 packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" |sudo tee /etc/apt/sources.list.d/vscode.list > /dev/null
rm -f packages.microsoft.gpg
```

```bash
sudo apt install apt-transport-https
sudo apt update
sudo apt install code # or code-insiders
```

### uv

La convention pour un projet Python est d'utiliser un environnement virtuel pour l'exécutable Python et les dépendances, ainsi que de considérer son propre code comme un package. Et le meilleur outil pour gérer tout cela à la fois est [`uv`](https://docs.astral.sh/uv/).

Pour [installer `uv`](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer) sur Ubuntu :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`uv` utilise le [`pyproject.toml`](pyproject.toml) pour créer son environnement virtuel. Pour créer (ou supprimer puis recréer) un environnement virtuel :

```bash
uv venv
```

Cela crée le venv avec la bonne version de Python, mais les librairies nécessaires n'y sont pas encore installées. Pour synchroniser le venv avec les librairies attendues dans le [`pyproject.toml`](pyproject.toml) :

```bash
uv sync
```

Voilà ! Maintenant notre venv est prêt. Si vous utilisez VSCode, vous pouvez sélectionner ce venv en faisant `CTRL+Maj+P` puis en sélectionnant `Python: Select Interpreter` ou simplement en cliquant sur l'interpréteur en bas à droite de l'écran en allant préalablement sur [un fichier Python](neorando/cli.py).

Vous remarquerez que la commande `uv sync` a créé automatiquement un fichier `uv.lock`. Ce fichier contient très exactement la version de toutes les librairies présentes dans le venv et permet donc de le reproduire à l'identique si nécessaire. Il serait tentant de ne pas l'inclure dans le git puisque c'est un fichier généré automatiquement, mais la convention est justement de l'inclure pour les raisons de reproductibilité évoquées précédemment. Si lors d'un merge, vous avez des conflits dans ce fichier, ne les réglez surtout pas à la main, réglez d'abord les conflits dans le [`pyproject.toml`](pyproject.toml) s'il y en a puis supprimez le `uv.lock` et regénérez-le avec `uv sync`.

Pour ajouter ou supprimer une dépendance :

```bash
uv add langchain      # ajouter
uv remove langchain   # supprimer
```

**Important** : `uv` remplace complètement `pip`, `pyenv`, `conda`, `poetry` ou tout autre outil de dependency/package management Python. N'utilisez surtout pas `pip` (ni `uv pip`). Si vous lisez quelque part que pour installer une librairie, il faut exécuter `pip install my-lib`, l'équivalent avec `uv` est `uv add my-lib`.

### Gitignore

Le [gitignore](.gitignore) fourni considère que vous utilisez VSCode. Si un membre de votre équipe utilise un autre IDE, nous vous invitons à compléter le gitignore avec les champs nécessaires pour l'IDE en question. Vous pouvez utiliser [gitignore.io](https://www.toptal.com/developers/gitignore).

### OpenAI

Pour pouvoir faire des appels à `gpt-5-mini` et `gpt-5-nano`, il faut utiliser votre clé API OpenAI. **Il ne faut surtout pas la push sur le Git !** Mettez-la dans un fichier `.env` qui est (déjà) dans le [gitignore](.gitignore) en suivant le modèle du [`.env.template`](.env.template).

Ensuite, chargez cette variable d'environnement dans votre code Python :

```python
from dotenv import load_dotenv

# Load the OPENAI_API_KEY from the .env file
load_dotenv()
```

## Structure du projet

```
neorando/
├── __init__.py
├── agent.py      ← Votre agent : implémentez answer_question()
├── cli.py        ← CLI (déjà câblée, appelle agent.answer_question)
├── schemas.py    ← Schéma Pydantic de réponse (ne pas modifier)
└── evaluation/   ← Code d'évaluation des soumissions (ne pas modifier)
```

**Votre point d'entrée principal** est la fonction `answer_question(question: str) -> AgentAnswer` dans `neorando/agent.py`. C'est cette fonction qui est appelée par la CLI pour chaque question. Vous êtes libres d'organiser le reste de votre code comme vous le souhaitez (ajouter des modules, des outils, etc.), tant que cette interface est respectée.

## CLI

Pour exécuter une commande via le venv créé par `uv`, utilisez `uv run` :

```bash
uv run neorando --help
```

L'utilisation de `uv run` est recommandée car avant d'exécuter votre script, `uv` effectue automatiquement un `uv sync` ce qui garantit que votre venv est bien à jour et synchronisé avec votre `pyproject.toml`, et cela peut éviter des bugs très bêtes.

Votre CLI est installée comme un tool Python dans votre venv grâce au champ suivant du `pyproject.toml` :

```toml
[project.scripts]
neorando = "neorando.cli:main"
```

**Remarque :** Une convention dans les CLI est de faire les imports lourds dans les fonctions de commandes si nécessaire, plutôt qu'en haut du fichier comme habituellement. Cela permet d'exécuter l'option `--help` quasi instantanément.

### Question unique

Pour tester votre agent sur une question (debug) :

```bash
uv run neorando query "Combien de randonnées sont référencées au total ?"
```

### Produire la soumission

Pour traiter toutes les questions et générer le fichier de soumission qui sera évalué :

```bash
uv run neorando run data/questions.csv -o submission.json
```

Le JSON produit contient les réponses et les statistiques de consommation API. Voir le [SUJET](SUJET.md#format-de-réponse) pour le détail du format.

### Évaluation

Pour évaluer votre soumission contre les réponses publiques :

```bash
# Évaluer avec les réponses par défaut (data/expected_answers.json)
uv run neorando eval submission.json

# Ou spécifier un autre fichier de réponses attendues
uv run neorando eval submission.json -e data/expected_answers.json
```

Le score global (0–100) et le détail par question seront affichés.

### Suivi de consommation

Pour voir combien de votre budget OpenAI il vous reste :

```bash
# Résumé : budget, consommé, restant
uv run neorando usage

# Détail par modèle (tokens, requêtes, coût)
uv run neorando usage --details
```

Cette commande utilise votre `OPENAI_API_KEY` (déjà dans votre `.env`) pour interroger le serveur de suivi.

### Ajout de commandes

Vous avez la liberté d'ajouter autant de commandes et d'options **documentées** que nécessaire dans `neorando/cli.py`. Par exemple, si votre pipeline nécessite une étape de préparation des données, rien ne vous empêche d'ajouter des commandes pour cela.

## Tests

Des tests `pytest` sont fournis dans le dossier `tests/` pour vérifier :

- Le schéma Pydantic `AgentAnswer` (sérialisation, validation)
- Le format de soumission JSON (clés requises, exactement un champ de réponse non-null, etc.)
- Le bon fonctionnement de la commande `neorando run` (avec un agent factice)
- L'interface de la fonction `answer_question` dans `neorando/agent.py`

```bash
uv run pytest
```

Au fur et à mesure de votre implémentation, vous pouvez ajouter vos propres tests.

## Notebooks

Si vous travaillez dans des notebooks et que vous voulez en push sur votre git, n'oubliez pas de les nettoyer avant :

```bash
uv run jupyter nbconvert --clear-output --inplace notebooks/*.ipynb
```

## Données

- [`data/questions.csv`](data/questions.csv) — les questions publiques (colonne `Query`)
- [`data/expected_answers.json`](data/expected_answers.json) — les réponses attendues à ces questions
- [`neorando/schemas.py`](neorando/schemas.py) — le schéma Pydantic de réponse
- [`neorando/agent.py`](neorando/agent.py) — votre agent (implémentez `answer_question()`)
- [`SUJET.md`](SUJET.md) — le sujet complet du hackathon
