import discord
import paramiko
import transformers
import sqlite3
import os
import json
from dotenv import load_dotenv
from discord.ext import commands

# Carregar as variáveis de ambiente do arquivo .env
load_dotenv()

# Criar uma instância do bot
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Acessar as variáveis de ambiente
bot_token = os.getenv("DISCORD_BOT_TOKEN")
api_key = os.getenv("API_KEY")
database_url = os.getenv("DATABASE_URL")

# Criar uma instância do cliente SSH
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

# Criar uma instância do modelo BART
model = transformers.BartForConditionalGeneration.from_pretrained("facebook/bart-large-cnn")
tokenizer = transformers.BartTokenizer.from_pretrained("facebook/bart-large-cnn")

# Criar uma conexão com o banco de dados
conn = sqlite3.connect("knowledge.db")
cursor = conn.cursor()

# Criar uma tabela para armazenar as informações dos usuários
cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, consent INTEGER)")

# Funções para consentimento
def get_consent(user):
    cursor.execute("SELECT * FROM users WHERE id = ?", (user.id,))
    result = cursor.fetchone()
    if result is None:
        cursor.execute("INSERT INTO users (id, name, consent) VALUES (?, ?, ?)", (user.id, user.name, 0))
        conn.commit()
        result = (user.id, user.name, 0)
    return result[2]

def update_consent(user, value):
    cursor.execute("UPDATE users SET consent = ? WHERE id = ?", (value, user.id))
    conn.commit()

# Função para criar contas na nuvem
def create_cloud_account(user, provider):
    if get_consent(user) == 1:
        if provider == "aws":
            import boto3
            iam = boto3.client("iam")
            username = user.name + str(user.id)
            iam.create_user(UserName=username)
            import secrets
            password = secrets.token_urlsafe(16)
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["ec2:DescribeInstances", "ec2:StartInstances", "ec2:StopInstances"],
                        "Resource": "*"
                    }
                ]
            }
            iam.put_user_policy(UserName=username, PolicyName="LimitedAccess", PolicyDocument=json.dumps(policy))
            access_key = iam.create_access_key(UserName=username)
            return (f"Conta criada na AWS com as seguintes credenciais:\nUsuário: {username}\nSenha: {password}\n"
                    f"Chave de Acesso: {access_key['AccessKeyId']}\nChave Secreta: {access_key['SecretAccessKey']}")
        elif provider == "gcp":
            from googleapiclient import discovery
            iam = discovery.build("iam", "v1")
            account_name = user.name + str(user.id)
            account = iam.projects().serviceAccounts().create(
                name="projects/my-project",
                body={"accountId": account_name, "serviceAccount": {"displayName": account_name}}
            ).execute()
            key = iam.projects().serviceAccounts().keys().create(name=account["name"], body={}).execute()
            return f"Conta criada no GCP com as seguintes credenciais:\nEmail: {account['email']}\nChave: {key['privateKeyData']}"
        elif provider == "azure":
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
            username = user.name + str(user.id)
            user = credential.create_user(UserName=username)
            import secrets
            password = secrets.token_urlsafe(16)
            role = credential.create_role(RoleName="LimitedAccess", RoleDefinition={
                "AssignableScopes": ["/subscriptions/my-subscription"],
                "Permissions": [
                    {"Actions": ["Microsoft.Compute/virtualMachines/read", "Microsoft.Compute/virtualMachines/start/action",
                                 "Microsoft.Compute/virtualMachines/stop/action"]}
                ]
            })
            credential.assign_role(RoleName=role, PrincipalId=user.id)
            return f"Conta criada no Azure com as seguintes credenciais:\nUsuário: {username}\nSenha: {password}"
        else:
            return "Provedor de nuvem inválido. Por favor, escolha entre aws, gcp ou azure."
    else:
        return "Você não tem o consentimento para criar contas na nuvem. Por favor, use o comando !consentir para dar o seu consentimento."

# Eventos e comandos do bot
@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")

@bot.command()
async def kali(ctx, *args):
    if args:
        commands = " ".join(args)
        try:
            stdin, stdout, stderr = ssh.exec_command(commands)
            output = stdout.read().decode()
            error = stderr.read().decode()
            if error:
                await ctx.send(f"Erro ao executar o comando:\n{error}")
            else:
                await ctx.send(f"Saída do comando:\n{output}")
        except Exception as e:
            await ctx.send(f"Ocorreu um erro: {str(e)}")
    else:
        await ctx.send("Por favor, forneça um comando para executar no Kali Linux. Exemplo: !kali ls -la")

@bot.command(aliases=["criar"])
async def criar(ctx, provider):
    if ctx.author.guild_permissions.administrator:
        response = create_cloud_account(ctx.author, provider)
        await ctx.send(response)
    else:
        await ctx.send("Você não tem permissão para usar este comando.")

@bot.command()
async def consentir(ctx):
    update_consent(ctx.author, 1)
    await ctx.send("Você deu o seu consentimento para criar contas na nuvem. Obrigado pela sua confiança.")

@bot.command()
async def retirar(ctx):
    update_consent(ctx.author, 0)
    await ctx.send("Você retirou o seu consentimento para criar contas na nuvem.")

@bot.command()
async def conversar(ctx, *args):
    if args:
        question = " ".join(args)
        input_ids = tokenizer(question, return_tensors="pt")
        output_ids = model.generate(input_ids['input_ids'], max_length=256)
        answer = tokenizer.decode(output_ids[0], skip_special_tokens=True)
        await ctx.send(answer)
    else:
        await ctx.send("Por favor, forneça uma pergunta para conversar com o bot. Exemplo: !conversar O que é inteligência artificial?")

bot.run(bot_token)