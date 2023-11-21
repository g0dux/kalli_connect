# Importar as bibliotecas necessárias
import discord
import paramiko
import transformers
import sqlite3
import os
from dotenv import load_dotenv
from discord.ext.commands import bot

# Carregar as variáveis de ambiente do arquivo .env
load_dotenv()

import discord

# Criar uma instância do bot
bot = discord.Client(intents=discord.Intents.all())

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

# Definir uma função para obter o consentimento do usuário para criar contas na nuvem
def get_consent(user):
  # Verificar se o usuário já está na tabela
  cursor.execute("SELECT * FROM users WHERE id = ?", (user.id,))
  result = cursor.fetchone()
  # Se o usuário não está na tabela, inserir um novo registro com consentimento igual a zero
  if result is None:
    cursor.execute("INSERT INTO users (id, name, consent) VALUES (?, ?, ?)", (user.id, user.name, 0))
    conn.commit()
    result = (user.id, user.name, 0)
  # Retornar o valor do consentimento do usuário
  return result[2]

# Definir uma função para atualizar o consentimento do usuário para criar contas na nuvem
def update_consent(user, value):
  # Atualizar o valor do consentimento do usuário na tabela
  cursor.execute("UPDATE users SET consent = ? WHERE id = ?", (value, user.id))
  conn.commit()

# Definir uma função para criar contas na nuvem usando as APIs dos provedores de nuvem
def create_cloud_account(user, provider):
  # Verificar se o usuário tem o consentimento para criar contas na nuvem
  if get_consent(user) == 1:
    # Escolher o provedor de nuvem de acordo com o parâmetro
    if provider == "aws":
      # Importar a biblioteca boto3 para interagir com a AWS
      import boto3
      # Criar um cliente para o serviço IAM da AWS
      iam = boto3.client("iam")
      # Gerar um nome de usuário aleatório usando o nome e o id do usuário
      username = user.name + str(user.id)
      # Criar um novo usuário na AWS usando o nome gerado
      iam.create_user(UserName=username)
      # Gerar uma senha aleatória usando a biblioteca secrets
      import secrets
      password = secrets.token_urlsafe(16)
      # Criar uma política de acesso para o usuário com permissões limitadas
      policy = {
        "Version": "2012-10-17",
        "Statement": [
          {
            "Effect": "Allow",
            "Action": [
              "ec2:DescribeInstances",
              "ec2:StartInstances",
              "ec2:StopInstances"
            ],
            "Resource": "*"
          }
        ]
      }
      # Anexar a política ao usuário
      iam.put_user_policy(UserName=username, PolicyName="LimitedAccess", PolicyDocument=json.dumps(policy))
      # Criar uma chave de acesso para o usuário
      access_key = iam.create_access_key(UserName=username)
      # Retornar as credenciais do usuário como uma string formatada
      return f"Conta criada na AWS com as seguintes credenciais:\nUsuário: {username}\nSenha: {password}\nChave de Acesso: {access_key['AccessKeyId']}\nChave Secreta: {access_key['SecretAccessKey']}"
    elif provider == "gcp":
      # Importar a biblioteca googleapiclient para interagir com o GCP
      from googleapiclient import discovery
      # Criar um cliente para o serviço IAM da GCP
      iam = discovery.build("iam", "v1")
      # Gerar um nome de conta de serviço usando o nome e o id do usuário
      account_name = user.name + str(user.id)
      # Criar uma nova conta de serviço no GCP usando o nome gerado
      account = iam.projects().serviceAccounts().create(
        name="projects/my-project",
        body={
          "accountId": account_name,
          "serviceAccount": {
            "displayName": account_name
          }
        }
      ).execute()
      # Gerar uma chave de acesso para a conta de serviço
      key = iam.projects().serviceAccounts().keys().create(
        name=account["name"],
        body={}
      ).execute()
      # Retornar as credenciais da conta de serviço como uma string formatada
      return f"Conta criada no GCP com as seguintes credenciais:\nEmail: {account['email']}\nChave: {key['privateKeyData']}"
    elif provider == "azure":
      # Importar a biblioteca azure.identity para interagir com o Azure
      from azure.identity import DefaultAzureCredential
      # Criar um cliente para o serviço Identity do Azure
      credential = DefaultAzureCredential()
      # Gerar um nome de usuário aleatório usando o nome e o id do usuário
      username = user.name + str(user.id)
      # Criar um novo usuário no Azure usando o nome gerado
      user = credential.create_user(UserName=username)
      # Gerar uma senha aleatória usando a biblioteca secrets
      import secrets
      password = secrets.token_urlsafe(16)
      # Criar uma função de acesso para o usuário com permissões limitadas
      role = credential.create_role(RoleName="LimitedAccess", RoleDefinition={
        "AssignableScopes": ["/subscriptions/my-subscription"],
        "Permissions": [
          {
            "Actions": [
              "Microsoft.Compute/virtualMachines/read",
              "Microsoft.Compute/virtualMachines/start/action",
              "Microsoft.Compute/virtualMachines/stop/action"
            ],
            "NotActions": [],
            "DataActions": [],
            "NotDataActions": []
          }
        ]
      })
      # Atribuir a função ao usuário
      credential.assign_role(RoleName=role, PrincipalId=user.id)
      # Retornar as credenciais do usuário como uma string formatada
      return f"Conta criada no Azure com as seguintes credenciais:\nUsuário: {username}\nSenha: {password}"
    else:
      # Retornar uma mensagem de erro se o provedor de nuvem não for reconhecido
      return f"Provedor de nuvem inválido. Por favor, escolha entre aws, gcp ou azure."
  else:
    # Retornar uma mensagem de aviso se o usuário não tiver o consentimento para criar contas na nuvem
    return f"Você não tem o consentimento para criar contas na nuvem. Por favor, use o comando !consentir para dar o seu consentimento."

# Definir um evento para quando o bot estiver pronto
@bot.event
async def on_ready():
  print(f"Bot conectado como {bot.user}")

# Definir um comando para interagir com o Kali Linux
@bot.commands.command()
async def kali(ctx, *args):
  # Verificar se os argumentos foram fornecidos
  if args:
    # Concatenar os argumentos em um único comando
    commands = " ".join(args)
    # Executar o comando no servidor Kali via SSH e obter a saída e o erro
    stdin, stdout, stderr = ssh.exec_command(commands)
    output = stdout.read().decode()
    error = stderr.read().decode()
    # Verificar se houve algum erro
    if error:
      # Enviar uma mensagem com o erro no Discord
      await ctx.send(f"Erro ao executar o comando:\n{error}")
    else:
      # Enviar uma mensagem com a saída no Discord
      await ctx.send(f"Saída do comando:\n{output}")
  else:
    # Enviar uma mensagem de ajuda no Discord
    await ctx.send(f"Por favor, forneça um comando para executar no Kali Linux. Exemplo: !kali ls -la")

# Definir um comando para criar contas na nuvem
@bot.commands.command(aliases=["criar"])
async def criar(ctx, provider):
  # Verificar se o usuário tem permissão para usar o comando
  if not ctx.author.permissions_in(ctx.guild).administrator:
    await ctx.send("Você não tem permissão para usar este comando.")
    return

  # Verificar se o provedor de nuvem foi fornecido
  if provider:
    # Chamar a função para criar contas na nuvem e obter a resposta
    response = create_cloud_account(ctx.author, provider)
    # Enviar uma mensagem com a resposta no Discord
    await ctx.send(response)
  else:
    # Enviar uma mensagem de ajuda no Discord
    await ctx.send(f"Por favor, forneça um provedor de nuvem para criar uma conta. Exemplo: !nuvem aws")

#Definir um comando para dar o consentimento para criar contas na nuvem
@bot.commands.command() 
async def consentir(ctx):
   #Atualizar o valor do consentimento do usuário para um na tabela
   update_consent(ctx.author, 1)
    #Enviar uma mensagem de confirmação no Discord
   await ctx.send(f"Você deu o seu consentimento para criar contas na nuvem. Obrigado pela sua confiança.")
#Definir um comando para retirar o consentimento para criar contas na nuvem
@bot.commands.command()
async def retirar(ctx):
     #Atualizar o valor do consentimento do usuário para zero na tabela
   update_consent(ctx.author, 0)
     #Enviar uma mensagem de confirmação no Discord
   await ctx.send(f"Você retirou o seu consentimento para criar contas na nuvem. Nenhuma conta será criada sem a sua permissão.")
#Definir um comando para conversar com o bot usando o modelo BART
@bot.commands.command() 
async def conversar(ctx, *args):
#Verificar se os argumentos foram fornecidos
    # Verificar se os argumentos foram fornecidos
  if args:
  # Concatenar os argumentos em uma única pergunta
   question= " ".join(args)
  # Codificar a pergunta usando o tokenizador do BART
   input_ids = tokenizer(question, return_tensors="pt")
  # Gerar uma resposta usando o modelo BART
   output_ids = model.generate(input_ids, max_length=256)
  # Decodificar a resposta usando o tokenizador do BART
   answer =tokenizer.decode(output_ids[0], skip_special_tokens=True)
  # Enviar uma mensagem com a resposta no Discord
   await ctx.send(answer)
  else: 
 #Enviar uma mensagem de ajuda no Discord 
    await ctx.send(F"Por favor, forneça uma pergunta para conversar com o bot. Exemplo: !conversar O que é inteligência artificial?")
bot.run("TOKEN")
