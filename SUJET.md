# Hackathon NSIGMA x NEOVISION 2026

## Planning

Ce hackathon dure 2 soirs pour un total de 8h :

* Mardi 10 mars de 18h à 22h, salles  E200-E201  
* Mercredi 11 mars de 18h à 22h, salles E200-E201

La révélation de l'équipe vainqueur ainsi que la remise des prix se feront le mardi 17 mars de 18h à 21h en amphi E, suivies d'une collation.

## Équipes

Ce hackathon peut se faire en équipe de 2 à 5 élèves.

## Classement

Durant ce hackathon, vous serez amené⋅es à développer une solution qui sera évaluée par Neovision avant la remise des prix. Ainsi, vous ne saurez si vous avez gagné qu'en venant le jour J.

Cependant, pour vous aider dans votre progression, un jeu de test "public" vous est fourni.

**Important** : Tout commit fait après 22h le mercredi 11 mars sera ignoré ! La version de votre projet qui sera prise en compte sera celle de votre branche `main`.

## Sujet

### Contexte

L'année dernière, vous avez dû construire un système RAG (Retrieval-Augmented Generation) pour répondre à des questions sur des documents PDF issus de Poképédia. Cette année, on passe à la vitesse supérieure : vous allez construire un **agent IA** capable de répondre à des questions sur les **randonnées autour de Grenoble**.

Les questions vont du plus simple (« Quel est le départ de telle randonnée ? ») au plus complexe (« Quelle randonnée est la plus rapide à rejoindre en voiture depuis tel endroit ? »). Votre agent devra être capable de :

1. **Récupérer les données** depuis le web
2. **Interroger** ces données de manière structurée
3. **Utiliser des outils géographiques** pour répondre aux questions spatiales (distances, itinéraires…)

### Source de données

La source de données est le site du tourisme de Grenoble, section randonnées à pied :

> **https://www.grenoble-tourisme.com/fr/faire/randonner/a-pied/**

C'est à votre agent de savoir comment exploiter cette source. Aucune autre donnée ne vous est fournie à part les questions.

### Types de questions

Voici la nature des questions auxquelles votre agent devra répondre :

- **Recherche simple** — retrouver une information précise concernant une randonnée (nom, commune, distance, URL…)
- **Agrégation** — compter, calculer des moyennes, trouver des extrema
- **Filtrage multi-critères** — combiner plusieurs conditions (niveau, type, commune, distance…)
- **Distance à vol d'oiseau** — calculer la distance entre un point donné et le départ d'une randonnée
- **Itinéraire routier** — calculer la durée ou la distance par la route en voiture entre un point donné et le départ d'une randonnée

### Contraintes

#### Modèle LLM

Vous devez utiliser **`gpt-5-mini`** en tant que LLM. Vous avez également accès à `gpt-5-nano` pour faire des tests moins chers.

Chaque équipe aura accès à une clé API OpenAI dédiée avec un budget limité de **5$**. Vous pouvez suivre votre consommation en temps réel avec `uv run neorando usage` (voir le [README](README.md#suivi-de-consommation)). **Surveillez votre budget régulièrement** pour ne pas vous retrouver à sec avant la fin du hackathon : vous n'aurez pas le droit à plus de budget.

#### Outils exclusivement open source

**Tous les outils et services externes que vous utilisez doivent être open source et gratuits.** Pas de Google Maps API, pas de Mapbox, pas de HERE, ni aucune autre API payante ou propriétaire.

Il existe des services de géocodage et de calcul d'itinéraire open source, utilisables sans clé API. C'est à vous de les identifier et de les intégrer à votre agent.

#### Reproductibilité

- Vous devez utiliser [`uv`](https://docs.astral.sh/uv/) comme package manager.
- Vos résultats doivent être **reproductibles** : à la fin du challenge, nous ferons tourner le code de chaque équipe sur un jeu de test privé pour déterminer le classement.
- Si votre projet nécessite toute autre installation que ce qui est gérable par `uv`, merci de le mentionner **clairement** dans un fichier complémentaire `installation.md`.
- Vous devez créer un repo GitHub **privé**, et ajouter l'utilisateur `lorisfloquet` comme collaborateur (voir le [README](README.md#github) pour la marche à suivre).

### Format de réponse

Votre agent doit retourner **exactement un** des champs suivants par question (déjà implémenté pour vous) :

| Champ | Type | Quand l'utiliser |
|-------|------|------------------|
| `answer` | `str` | La question attend **une seule valeur textuelle** (nom de rando, commune, URL, type de parcours, niveau…) |
| `numeric` | `float` | La question attend **un nombre** (distance en km, durée en minutes, dénivelé, comptage…) |
| `boolean` | `bool` | La question attend **oui ou non** |
| `items` | `list[str]` | La question attend **plusieurs valeurs** (liste de noms de randonnées, de communes…) |

Les autres champs doivent être `None`. Le schéma Pydantic complet est fourni dans [`neorando/schemas.py`](neorando/schemas.py).

### Évaluation

Chaque réponse est évaluée automatiquement avec un score entre 0 et 1 (code d'évaluation fourni) :

- **Texte** : matching normalisé (insensible à la casse et aux accents), exact ou fuzzy selon la question
- **Numérique** : erreur relative avec tolérance (généralement 5%, davantage pour les valeurs issues de calculs d'itinéraire)
- **Booléen** : correspondance exacte
- **Liste** : score F1 basé sur le matching fuzzy de chaque élément

Le **score global** est la moyenne des scores de toutes les questions, normalisée de 0 à 100. Vous pouvez évaluer votre soumission localement à tout moment (voir le [README](README.md#évaluation)).

**Important** : En cas d'égalité en termes de points entre plusieurs équipes du podium, les équipes dont l'agent consomme le moins de tokens totaux pour répondre aux questions seront avantagées (correspond à `total_prompt_tokens` + `total_completion_tokens` de la section `usage` du JSON de soumission).

## Données et accès

Données fournies dans le template :

- [`data/questions.csv`](data/questions.csv) — les questions publiques (colonne `Query`)
- [`data/expected_answers.json`](data/expected_answers.json) — les réponses attendues à ces questions

Données fournies par mail au début du hackathon :

- Clé API OpenAI par équipe (à mettre dans votre `.env`)

Consultez absolument le [README](README.md) pour l'installation, l'utilisation de la CLI et le guide technique complet.

## Conseils (non obligatoires)

- **Commencez par explorer la source de données** avant de coder quoi que ce soit. Comprenez la structure du site, les informations disponibles, et comment les extraire.
- **Répartissez-vous bien les tâches** : le sujet est conçu avec des tâches bien identifiables.
- Nous vous recommandons fortement d'utiliser [LangChain](https://github.com/langchain-ai/langchain) ou même [LangGraph](https://github.com/langchain-ai/langgraph) pour orchestrer votre agent, mais ce n'est pas obligatoire.
- Activez le mode debug de votre framework pour vérifier que tout se passe bien à chaque prompt. Avec LangChain : `from langchain_core.globals import set_debug; set_debug(True)`.
- Utilisez [Ruff](https://docs.astral.sh/ruff/) comme formateur / linter Python.
- N'hésitez pas à expérimenter dans des notebooks Jupyter, mais nettoyez-les avant de les push (`uv run jupyter nbconvert --clear-output --inplace notebooks/*.ipynb`).
