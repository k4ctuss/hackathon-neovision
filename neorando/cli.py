import json
import sys
import time
from datetime import datetime
from pathlib import Path

import rich_click as click


@click.group()
@click.version_option()
def main() -> None:
    """🥾 NeoRando — Agent Randonnées Grenoble"""


# ── query ────────────────────────────────────────────────────────────────────


@main.command("query")
@click.argument("question", nargs=1)
def query_cmd(question: str) -> None:
    """Pose une QUESTION à l'agent et affiche la réponse JSON sur stdout."""
    from openai_callback import track_usage

    from neorando.agent import answer_question

    with track_usage() as usage:
        ans = answer_question(question, history=[])
        

    click.echo(ans.model_dump_json(indent=2, exclude_none=True))
    click.echo(
        f"\n💰 {usage.prompt_tokens} prompt + {usage.completion_tokens} completion tokens — ${usage.total_cost:.6f}",
        err=True,
    )


# ── run ──────────────────────────────────────────────────────────────────────


def _default_output() -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = Path(__file__).parents[1]
    return root / f"output/answer_{ts}.json"


@main.command("run")
@click.argument("input-csv", nargs=1, type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    "output_json",
    default=None,
    show_default="output/answer_{timestamp}.json",
    help="Fichier JSON de sortie.",
)
def run_cmd(input_csv: str, output_json: str) -> None:
    """Traite toutes les questions de INPUT_CSV et produit un fichier de soumission JSON.

    INPUT_CSV doit contenir une colonne 'Query'.

    Le JSON de sortie est une liste d'objets conformes au schéma AgentAnswer
    (voir neorando/schemas.py), avec en plus les champs 'query' et 'time'.
    """
    import pandas
    from openai_callback import track_usage
    from tqdm import tqdm

    from neorando.agent import answer_question
    from neorando.schemas import AgentAnswer
    from langchain_core.messages import BaseMessage, HumanMessage
    from typing import List


    if output_json is None:
        output_json = _default_output()

    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pandas.read_csv(input_csv)
    if "Query" not in df.columns:
        click.echo("❌ Le CSV doit contenir une colonne 'Query'.", err=True)
        sys.exit(1)

    results: list[dict] = []
    history: List[BaseMessage] = []
    with track_usage() as total_usage:
        pbar = tqdm(df.iterrows(), total=len(df), desc="Questions")
        for _i, row in pbar:
            question = row["Query"]
            t0 = time.time()
            try:
                with track_usage() as question_usage:
                    ans = answer_question(question, history)
            except Exception:
                click.secho(
                    f"⚠️  Erreur pour la question {_i} : {question!r}",
                    err=True,
                    fg="yellow",
                )
                ans = AgentAnswer.model_construct()
                question_usage = None
            elapsed = time.time() - t0

            pbar.set_postfix_str(f"${total_usage.total_cost:.4f}")

            entry: dict = {
                "query": question,
                "answer": ans.answer,
                "numeric": ans.numeric,
                "boolean": ans.boolean,
                "items": ans.items,
                "time": round(elapsed, 2),
            }
            if question_usage is not None:
                entry["usage"] = {
                    "prompt_tokens": question_usage.prompt_tokens,
                    "completion_tokens": question_usage.completion_tokens,
                    "reasoning_tokens": question_usage.reasoning_tokens,
                    "cached_tokens": question_usage.cached_tokens,
                    "total_cost": round(question_usage.total_cost, 8),
                    "models": sorted(question_usage.models),
                }

            results.append(entry)

    submission = {
        "results": results,
        "usage": {
            "total_prompt_tokens": total_usage.prompt_tokens,
            "total_completion_tokens": total_usage.completion_tokens,
            "total_reasoning_tokens": total_usage.reasoning_tokens,
            "total_cached_tokens": total_usage.cached_tokens,
            "total_requests": total_usage.requests,
            "total_cost_usd": round(total_usage.total_cost, 8),
            "models": sorted(total_usage.models),
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(submission, f, ensure_ascii=False, indent=2)

    click.echo(f"✅ Soumission écrite : {output_path} ({len(results)} questions)")
    click.echo(
        f"💰 Usage total : {total_usage.prompt_tokens} prompt + "
        f"{total_usage.completion_tokens} completion tokens "
        f"({total_usage.reasoning_tokens} reasoning) — "
        f"${total_usage.total_cost:.6f}"
    )


# ── eval ─────────────────────────────────────────────────────────────────────


@main.command("eval")
@click.argument("submission-json", nargs=1, type=click.Path(exists=True))
@click.option(
    "-e",
    "--expected",
    "expected_json",
    default=None,
    show_default="data/expected_answers.json",
    help="Fichier JSON des réponses attendues.",
)
def eval_cmd(submission_json: str, expected_json: str | None) -> None:
    """Évalue un fichier de soumission SUBMISSION_JSON contre les réponses attendues.

    Affiche le score global et le détail des questions échouées.
    """
    if not submission_json.endswith(".json"):
        click.secho(
            f"❌ Le fichier de soumission doit être un JSON, reçu : {submission_json}",
            err=True,
            fg="red",
        )
        sys.exit(1)

    from neorando.evaluation.eval import (
        DEFAULT_EXPECTED,
        eval_submission,
        print_results,
    )

    expected = expected_json or str(DEFAULT_EXPECTED)
    results = eval_submission(submission_json, expected)
    print_results(results)


# ── usage ────────────────────────────────────────────────────────────────────

HACKATHON_API_URL = "https://hackathon.neovision.fr"


@main.command("usage")
@click.option(
    "--details",
    is_flag=True,
    default=False,
    help="Afficher le détail par modèle.",
)
def usage_cmd(details: bool) -> None:
    """Affiche la consommation OpenAI de votre équipe (budget restant, coût…)."""
    import os

    import requests
    from dotenv import load_dotenv

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        click.secho(
            "❌ OPENAI_API_KEY non définie dans l'environnement.", err=True, fg="red"
        )
        sys.exit(1)

    endpoint = "/usage/details" if details else "/usage"
    url = f"{HACKATHON_API_URL.rstrip('/')}{endpoint}"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except requests.ConnectionError:
        click.secho(
            "❌ Impossible de joindre le serveur de consommation.", err=True, fg="red"
        )
        sys.exit(1)

    if resp.status_code == 401:
        click.secho("❌ Clé API manquante ou invalide.", err=True, fg="red")
        sys.exit(1)
    if resp.status_code == 403:
        click.secho("❌ Clé API non reconnue par le serveur.", err=True, fg="red")
        sys.exit(1)
    if resp.status_code != 200:
        click.secho(f"❌ Erreur serveur ({resp.status_code}).", err=True, fg="red")
        sys.exit(1)

    data = resp.json()

    # Header
    team = data["team_name"]
    used = data["used_usd"]
    budget = data["budget_usd"]
    remaining = data["remaining_usd"]
    pct = data["percentage_used"]

    color = "green" if pct < 50 else ("yellow" if pct < 80 else "red")

    click.echo()
    click.secho(f"  📊 {team}", bold=True)
    click.echo(f"  Budget :     ${budget:.2f}")
    click.secho(f"  Consommé :   ${used:.4f}  ({pct:.1f}%)", fg=color)
    click.echo(f"  Restant :    ${remaining:.4f}")

    if details and "models" in data:
        click.echo()
        click.secho("  Détail par modèle :", bold=True)
        for m in data["models"]:
            click.echo(
                f"    • {m['model']:30s}  "
                f"{m['requests']:>4d} req  "
                f"{m['input_tokens']:>8d} in  "
                f"{m['output_tokens']:>8d} out  "
                f"${m['cost_usd']:.6f}"
            )

    click.echo()


# ── scrape ──────────────────────────────────────────────────────────────────


@main.command("scrape")
def scrape_cmd() -> None:
    """Pré-scrape toutes les randonnées du site et sauvegarde dans data/hikes.json.

    À lancer UNE FOIS avant d'utiliser l'agent. Les données seront ensuite
    chargées automatiquement par l'agent pour répondre aux questions.
    """
    import asyncio

    from neorando.scraper import CACHE_PATH, scrape_and_save

    click.echo("🔍 Scraping de toutes les randonnées en cours...")
    hikes = asyncio.run(scrape_and_save())
    click.echo(f"✅ {len(hikes)} randonnées sauvegardées dans {CACHE_PATH}")

    # Quick summary
    with_coords = sum(1 for h in hikes if h.get("latitude"))
    with_dist = sum(1 for h in hikes if h.get("distance_km"))
    with_dur = sum(1 for h in hikes if h.get("duree_min"))
    with_diff = sum(1 for h in hikes if h.get("difficulte"))
    click.echo(
        f"   📊 Coords GPS: {with_coords} | Distance: {with_dist} | "
        f"Durée: {with_dur} | Difficulté: {with_diff}"
    )


if __name__ == "__main__":
    main()
