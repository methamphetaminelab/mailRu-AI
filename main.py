from otvetmailru import OtvetClient
from g4f.client import Client
from g4f.Provider import Blackbox
from g4f.models import llama_3_3_70b
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typing import Dict
import os
import random
import re

console = Console()
AUTH_FILE = 'auth_info.txt'

def authenticate_client() -> Dict[OtvetClient, Client]:
    client = None
    g4f_client = Client()
    
    if os.path.isfile(AUTH_FILE):
        with open(AUTH_FILE) as f:
            client = OtvetClient(auth_info=f.read())
    else:
        client = OtvetClient()
    
    if not client.check_authentication():
        email = console.input('[bold cyan]Email> [/bold cyan]')
        password = console.input('[bold cyan]Password> [/bold cyan]')
        client.authenticate(email, password)
        with open(AUTH_FILE, 'w') as f:
            f.write(client.auth_info)
    
    return client, g4f_client

def contains_link_or_image(text: str) -> bool:
    url_pattern = re.compile(r'https?://\S+')
    image_pattern = re.compile(r'!\[.*\]\(.*\)|<img\s+[^>]*src="[^"]+"')
    return bool(url_pattern.search(text) or image_pattern.search(text))

def process_question(client, g4f_client, question_id) -> None:
    question = client.get_question(question_id)
    if not question.can_answer:
        return

    if contains_link_or_image(question.title) or contains_link_or_image(question.text):
        console.print("[bold yellow]Вопрос пропущен, так как содержит ссылку или изображение.[/bold yellow]\n")
        return

    header = Text()
    header.append("Автор: ", style="bold yellow")
    header.append(f"{question.author.name}  ")
    header.append("| Категория: ", style="bold yellow")
    header.append(f"{question.category.name}")

    url_text = Text.assemble(("URL: ", "bold green"), (question.url, "underline blue"))
    title_text = Text.assemble(("Заголовок: ", "bold magenta"), (question.title, "italic"))
    question_panel = Panel(question.text, title="Текст вопроса", title_align="left", style="cyan")

    console.rule("[bold red]Новый вопрос[/bold red]")
    console.print(header)
    console.print(url_text)
    console.print(title_text)
    console.print(question_panel)

    if not question.poll_type:
        try:
            system_prompt = (
                "Ты квалифицированный эксперт, всегда дающий подробные и точные ответы. "
                "Ответь максимально подробно, кратко, аргументированно и на русском языке."
            )
            user_prompt = f"ЗАГОЛОВОК: {question.title}\nВОПРОС: {question.text}"
            
            response = g4f_client.chat.completions.create(
                model=llama_3_3_70b,
                provider=Blackbox,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                web_search=False
            )
            
            ai_answer = response.choices[0].message.content.strip()
            answer_panel = Panel(ai_answer, title="Ответ от ИИ", title_align="left", style="green")
            console.print(answer_panel)
            
            client.add_answer(question, ai_answer)
            
        except Exception as e:
            if "limits exceeded: AAQ" in str(e) or "Expecting value" in str(e):
                client.add_answer(question, ai_answer)
                console.print("[bold green]Ответ опубликован автоматически.[/bold green]\n")
            else:
                console.print(f"[bold red]Ошибка при запросе к ИИ: {e}[/bold red]\n")
    else:
        poll_table = Table(title="Опрос", show_header=True, header_style="bold blue")
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
            console.print("[bold green]Голос учтён автоматически.[/bold green]\n")
        except Exception as e:
            console.print(f"[bold red]Ошибка при голосовании: {e}[/bold red]\n")

def main() -> None:
    client, g4f_client = authenticate_client()
    me = client.get_user()
    
    profile_info = (
        f"[bold yellow]Пользователь ID:[/bold yellow] {client.user_id}\n"
        f"[bold yellow]Имя:[/bold yellow] {me.name}\n"
        f"[bold yellow]Рейтинг:[/bold yellow] {me.rate.name}\n"
        f"[bold yellow]Профиль:[/bold yellow] [underline blue]{me.url}[/underline blue]"
    )
    profile_panel = Panel(profile_info, title="Профиль пользователя", style="magenta")
    console.print(profile_panel)
    
    for questions in client.iterate_new_questions():
        for question_id in questions:
            process_question(client, g4f_client, question_id)

if __name__ == '__main__':
    main()
