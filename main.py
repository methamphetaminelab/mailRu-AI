from otvetmailru import OtvetClient
from otvetmailru.models import QuestionPreview
from otvetmailru.error import OtvetAuthError
from g4f.client import Client
from g4f.Provider import Blackbox
from g4f.models import llama_3_3_70b
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import Dict, List
import random
import json
import sys
import re
import os

AUTH_FILE = "accounts.json"
PROGRAM_VERSION = "1.1.4c"
PROGRAM_NAME = "mailRu AI"
console = Console()

def create_info_panel(panel_title: str, info: dict, border_style: str = "blue") -> Panel:
    table = Table.grid(padding=(0, 1))
    table.expand = True
    table.add_column(justify="left", style="bold cyan", no_wrap=True)
    table.add_column(justify="left", style="white")
    for key, value in info.items():
        table.add_row(f"{key}:", str(value))
    return Panel(table, title=panel_title, border_style=border_style, padding=(0, 0))


def display_startup_info() -> None:
    settings = {
        "Program": PROGRAM_NAME,
        "Version": PROGRAM_VERSION,
        "Auth File": AUTH_FILE,
        "AI Model": "llama-3.3-70b",
        "Provider": "Blackbox",
        "Mode": "Answering questions / Voting in polls"
    }
    settings_panel = create_info_panel("Program Settings", settings, border_style="blue")
    console.print(settings_panel)


def load_accounts() -> List[Dict[str, str]]:
    if os.path.isfile(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                accounts = json.load(f)
                if isinstance(accounts, list):
                    return accounts
        except Exception as e:
            console.print(f"[red]Ошибка при загрузке аккаунтов: {e}[/red]")
    return []


def save_accounts(accounts: List[Dict[str, str]]) -> None:
    try:
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=4, ensure_ascii=False)
    except Exception as e:
        console.print(f"[red]Ошибка при сохранении аккаунтов: {e}[/red]")


def add_new_account() -> Dict[str, str]:
    client = OtvetClient()
    email = console.input("[bold cyan]Email> [/bold cyan]")
    password = console.input("[bold cyan]Password> [/bold cyan]")
    try:
        client.authenticate(email, password)
        if not client.check_authentication():
            console.print("[red]Аутентификация не удалась. Попробуйте ещё раз.[/red]")
            return add_new_account()
    except OtvetAuthError:
        console.print("[red]Аутентификация не удалась. Попробуйте ещё раз.[/red]")
        return add_new_account()
    console.print(f"[green]Аккаунт {email} успешно добавлен.[/green]")
    return {"email": email, "auth_info": client.auth_info}


def select_account() -> OtvetClient:
    accounts = load_accounts()

    while True:
        if accounts:
            console.print("\n[bold]Доступные аккаунты:[/bold]")
            for i, account in enumerate(accounts, 1):
                console.print(f"[{i}] {account['email']}")
            choice = console.input("Выберите номер аккаунта или введите 'a' для добавления, 'r' для удаления: ").strip().lower()

            if choice == "a":
                new_account = add_new_account()
                accounts.append(new_account)
                save_accounts(accounts)
                selected = new_account
                break
            elif choice == "r":
                remove_choice = console.input("Введите номер аккаунта для удаления: ").strip()
                try:
                    index = int(remove_choice) - 1
                    if index < 0 or index >= len(accounts):
                        console.print("[red]Неверный номер аккаунта.[/red]")
                        continue
                    removed = accounts.pop(index)
                    save_accounts(accounts)
                    console.print(f"[green]Аккаунт {removed['email']} удалён.[/green]")
                    continue
                except ValueError:
                    console.print("[red]Некорректный ввод.[/red]")
                    continue
            else:
                try:
                    index = int(choice) - 1
                    if index < 0 or index >= len(accounts):
                        console.print("[red]Неверный номер аккаунта.[/red]")
                        continue
                    selected = accounts[index]
                    break
                except ValueError:
                    console.print("[red]Некорректный ввод.[/red]")
                    continue
        else:
            console.print("[yellow]Нет доступных аккаунтов. Добавьте новый.[/yellow]")
            new_account = add_new_account()
            accounts.append(new_account)
            save_accounts(accounts)
            selected = new_account
            break

    client = OtvetClient(auth_info=selected["auth_info"])
    if not client.check_authentication():
        console.print(f"[yellow]Сохранённая аутентификация для {selected['email']} недействительна. Повторная аутентификация...[/yellow]")
        password = console.input(f"[bold cyan]Введите пароль для {selected['email']}> [/bold cyan]")
        client.authenticate(selected["email"], password)
        if client.check_authentication():
            selected["auth_info"] = client.auth_info
            for account in accounts:
                if account["email"] == selected["email"]:
                    account["auth_info"] = client.auth_info
                    break
            save_accounts(accounts)
        else:
            console.print("[red]Аутентификация не удалась. Попробуйте ещё раз.[/red]")
            return select_account()
    return client


def contains_link_or_image(text: str) -> bool:
    url_pattern = re.compile(r"https?://\S+")
    image_pattern = re.compile(r"!\[.*\]\(.*\)|<img\s+[^>]*src=\"[^\"]+\"")
    return bool(url_pattern.search(text) or image_pattern.search(text))


def process_question(client: OtvetClient, g4f_client: Client, question_id: QuestionPreview) -> None:
    question = client.get_question(question_id)
    if not question.can_answer:
        return

    if contains_link_or_image(question.title) or contains_link_or_image(question.text):
        skip_panel = Panel(
            "[yellow]Вопрос пропущен, так как содержит ссылку или изображение.[/yellow]",
            title="Пропущено",
            border_style="yellow",
            padding=(0, 1)
        )
        console.print(skip_panel)
        return

    metadata = {
        "Автор": question.author.name,
        "Категория": question.category.name,
        "URL": question.url,
        "Заголовок": question.title
    }
    metadata_panel = create_info_panel("Метаданные вопроса", metadata, border_style="blue")

    console.rule("[bold red]Новый вопрос[/bold red]")
    console.print(metadata_panel)

    question_panel = Panel(
        question.text,
        title="Текст вопроса",
        border_style="cyan",
        padding=(0, 1)
    )
    console.print(question_panel)

    if not question.poll_type:
        try:
            system_prompt = (
                "Ты квалифицированный эксперт, всегда дающий ПОДРОБНЫЕ и ТОЧНЫЕ ответы. "
                "Ответь максимально подробно, кратко, аргументированно и на РУССКОМ языке. "
                "Использовать markdown формат для ответа НЕ нужно."
            )
            user_prompt = f"ЗАГОЛОВОК: {question.title}\nВОПРОС: {question.text}"

            response = g4f_client.chat.completions.create(
                model=llama_3_3_70b,
                provider=Blackbox,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                web_search=False
            )

            ai_answer = response.choices[0].message.content.strip()
            answer_panel = Panel(
                ai_answer,
                title="Ответ AI",
                border_style="green",
                padding=(0, 1)
            )
            console.print(answer_panel)

            client.add_answer(question, ai_answer)

        except Exception as e:
            error_message = str(e)
            if "Expecting value: line 1 column 1 (char 0)" in error_message:
                error_panel = Panel(
                    f"[red]Ошибка в запросе к AI: {e}[/red]",
                    title="Ошибка",
                    border_style="red",
                    padding=(0, 1)
                )
                console.print(error_panel)
            elif "limits exceeded: AAQ" in error_message:
                error_panel = Panel(
                    "[red]Достигнут дневной лимит ответов для этого аккаунта.[/red]",
                    title="Ошибка",
                    border_style="red",
                    padding=(0, 1)
                )
                console.print(error_panel)
                sys.exit(1)
            else:
                error_panel = Panel(
                    f"[red]Ошибка в запросе к AI: {e}[/red]",
                    title="Ошибка",
                    border_style="red",
                    padding=(0, 1)
                )
                console.print(error_panel)
    else:
        poll_table = Table(title="Опрос", show_header=True, header_style="bold blue", expand=True, pad_edge=False)
        poll_table.add_column("№", justify="center")
        poll_table.add_column("Вариант ответа", justify="left")
        for i, option in enumerate(question.poll.options, 1):
            poll_table.add_row(str(i), option.text)
        console.print(poll_table)

        try:
            vote_indices = random.sample(
                range(1, len(question.poll.options) + 1),
                random.randint(1, len(question.poll.options))
            )
            selected = [question.poll.options[i - 1] for i in vote_indices]
            client.vote_in_poll(question, selected)
            vote_panel = Panel(
                "[green]Ваш голос успешно зарегистрирован автоматически.[/green]",
                title="Голосование",
                border_style="green",
                padding=(0, 1)
            )
            console.print(vote_panel)
        except Exception as e:
            error_panel = Panel(
                f"[red]Ошибка при голосовании: {e}[/red]",
                title="Ошибка голосования",
                border_style="red",
                padding=(0, 1)
            )
            console.print(error_panel)


def main() -> None:
    welcome_panel = Panel(
        Text("mailRu AI Answer Bot", justify="center", style="bold magenta"),
        border_style="blue",
        padding=(0, 1)
    )
    console.print(welcome_panel)

    display_startup_info()

    client = select_account()
    g4f_client = Client()

    me = client.get_user()
    profile = {
        "User ID": client.user_id,
        "Имя": me.name,
        "Рейтинг": me.rate.name,
        "Профиль": me.url
    }
    profile_panel = create_info_panel("Профиль пользователя", profile, border_style="magenta")
    console.print(profile_panel)

    for questions in client.iterate_new_questions():
        for question_id in questions:
            process_question(client, g4f_client, question_id)


if __name__ == "__main__":
    main()
