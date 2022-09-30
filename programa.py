from fileinput import filename
import os
import io
from sys import exc_info
from time import sleep
from random import randint, random

import PySimpleGUI as sg
import requests

#ATENÇÃO!!! veja a documentação para usar o pytesseract
#https://pypi.org/project/pytesseract/
#https://github.com/tesseract-ocr/tesseract
#https://github.com/UB-Mannheim/tesseract/wiki
import pytesseract
from PIL import Image 
from pdf2image import convert_from_path 

from googletrans import Translator
import configparser
from gtts import gTTS
from audioplayer import AudioPlayer
import glob

#ATENÇÂO!!! veja a documentação para usar o pydub
#https://github.com/jiaaro/pydub#installation
#repara que para a conversão para mp3 é necessario o ffmpeg
#e devidamente configurado na váriavel de ambiente ou na pasta bin do projeto
from pydub import AudioSegment

#define duas keys para os textos multi-linhas
ML_TRADUZIDA = "-ML_TRADUZIDA-"
ML_ORIGINAL = "-ML_ORIGINAL-"

#define mais um key para o texto multi-linhas que representa o LOG
ML_LOG = "-LOG-"

#testa se existe uma conexão com a internet
def testa_conexao():
    """
    Teste se existe uma conexão com a internet\n
    Enviando um request para o google\n
    <- bool return - retorna True em caso positivo
    """
    url = "https://www.google.com/"
    timeout = 5
    try:
        request = requests.get(url, timeout=timeout)
        return True
    except (requests.ConnectionError, requests.Timeout) as exception:
        return False


#mostra a mensagem informada, usando um popup com barra de rolagem
def mostra_erro(mensagem):
    sg.popup_scrolled(mensagem, auto_close=True, auto_close_duration=30)


#mostra a mensagem informada, no campo LOG da janela principal
def fazer_log(H_janela, mensagem = "", cor = 'black'):
    """
    Imprime no campo LOG as mensagens geradas pelo processamento\n
    -> handler H_Janela - referencia para a janela criada pelo pySimpleGUI\n
    -> string mensagem - a mensagem a ser mostrada\n
    -> string cor - a cor do texto\n
    <- void retorno - essa função não tem um valor de retorno
    """
    sg.cprint_set_output_destination(H_janela, ML_LOG)
    sg.cprint(mensagem, text_color=cor)
    H_janela.refresh()


#cria o arquivo config.ini, para armazenar algumas informações
def set_configuracao_ini(H_janela = None, arquivo_pdf = "pdf", pg_traduzida = 0, pg_vista=0):
    """
    Salva o caminho onde está o PDF selecionado\n
    Salva o número da ultima página traduzida\n
    O aqruivo chama-se config.ini e será salvo na mesma pasta do scritp\n
    -> handler H_janela - quando definido salva o numero da ultima pagina lida\n
    -> str arquivo_pdf - caminho e nome do arquivo PDF, ignorado se H_janela for espeficicado\n
    -> int pg_traduzida - numero da ultima pagina traduzida, ignorado se H_janela for espeficicado\n
    -> int pg_vista - numero da ultima pagina lida.\n
    <- return - essa função não tem dados de retorno.
    """
    NOME_INI = "config.ini"

    config = configparser.ConfigParser()
    if os.path.exists(NOME_INI):
        config.read(NOME_INI)
        if pg_traduzida > 0: config['DADOS']['pagina'] = str(pg_traduzida)
        if arquivo_pdf != "pdf": config['DADOS']['caminho'] = arquivo_pdf
        if H_janela != None: config['DADOS']['ultimaVista'] = str(pg_vista)
    else:
        config.add_section("DADOS")
        config.set("DADOS", "pagina", str(pg_traduzida))
        config.set("DADOS", "caminho", arquivo_pdf)
        config.set("DADOS", "ultimaVista", str(pg_vista))

    with open(NOME_INI, 'w') as configfile:
        config.write(configfile)


#retorna as informações slavas no config.ini, caso ele exista
def get_configuracoes_ini(H_janela = None, sessao = 0):
    """
    Retorna a configuração gravada no arquivo .ini\n
    -> handle H_janela - se for espeficicada retorna a ultima pagina vista\n
    -> int sessao - 1 = ultima pagina traduzida, 2 = caminho do pdf
    <- return str/None - retorna uma string ou None. 
    """
    NOME_INI = "config.ini"
    retorno = None
    config = configparser.ConfigParser()
    if os.path.exists(NOME_INI):
       config.read(NOME_INI)
       if H_janela != None:
            retorno = config['DADOS']['ultimaVista'] 
            return retorno

       if sessao == 1:
             retorno = config['DADOS']['pagina']
       elif sessao == 2:
            retorno = config['DADOS']['caminho']
    
    return retorno


# ---------------------------------inicio funções responsaveis pela tradução ---------------------------------
#converte uma página do pdf, para uma imagem
def escanear_pagina(pg_numero, H_janela):
    """
    Converte a pagina informada em uma imagem\n
    -> int pg_numero - numero da pagina a ser escaneada\n
    -> handler H_janela - uma referencia para janela criada pelo pySimpleGUI\n
    <- bool return - retorna True se a página foi escaneada corretamente
    """
    pdf_informado = H_janela["-ARQUIVO_PDF-"].get()
    if pdf_informado == "":
        fazer_log(H_janela,f"Selecione o arquivo PDF pelo botão Browser")
        return False
    
    if not os.path.exists(pdf_informado):
        fazer_log(H_janela,f"O arquivo PDF informado não foi localizado, selecione o arquivo PDF pelo botão Browser")
        return False

    pages = convert_from_path(pdf_informado, 300,first_page=pg_numero, last_page=pg_numero)
    imagem = f"{os.getcwd()}/imagens/pagina_{pg_numero}.jpg"
    if os.path.exists(imagem):
        questao = sg.popup_yes_no('A imagem dessa página já existe.', 'Clique em [Yes] se deseja criar novamente.')
        if questao == 'Yes':
          try:
              pages[0].save(imagem, 'JPEG')
              fazer_log(H_janela,f"Imagem da pagina_{pg_numero}, criada com sucesso")
              return True
          except:
              fazer_log(H_janela,f'Ocorreu um erro ao tentar salvar a imagem da página_{pg_numero}')        
              return False

    fazer_log(H_janela,f"A imagem da pagina_{pg_numero}, já existe. Ignorando...")
    return True


#converte a imagem gerada, em um arquivo de texto
def converte_para_texto(pg_numero, H_janela):
    """
    Converte a imagem escaneada em texto\n
    -> int pg_numero - numero da pagina que o texto será extraido\n
    -> handler H_janela - uma referencia a janela criada pelo pySimpleGUI\n
    <- bool return - retorna True se o texto for extraido com sucesso
    """
    imagem = os.getcwd() + "/imagens/pagina_" + str(pg_numero)+".jpg"
    if not os.path.exists(imagem):
        fazer_log(H_janela,f"Arquivo {imagem} , não foi encontrado")
        return False

    destino = os.getcwd() + f"/escaneado/pagina_{pg_numero}.txt"
    if os.path.exists(destino):
        questao = sg.popup_yes_no('O texto dessa página já existe.', 'Clique em [Yes] se desejar criar novamente.')
        if questao == 'Yes':
          try:
              texto = str(((pytesseract.image_to_string(Image.open(imagem)))))
              #texto = texto.replace('-\n', '')
              f = open(destino, "a")
              f.write(texto)
              f.close()
              fazer_log(H_janela,f"Imagem da pagina_{pg_numero}, convertida em texto com sucesso")
              return True
          except:
              fazer_log(H_janela,f"Ocorreu um erro na conversão da Imagem da pagina_{pg_numero}")
              return False

    fazer_log(H_janela,f"Texto original da pagina_{pg_numero}, já existe. Ignorando...")
    return True


#utiliza o google translator para traduzir a página
def traduzir_texto(pg_numero, H_janela):
    """
    Traduz o texto extraido da imagem, aqui é usado o serviço do\n
    google translate, o código faz até 3 tentativas caso ocorra\n
    algum erro na rede, repare nos [sleep] entre cada chamada.\n
    -> int pg_numero - numero da pagina que o texto será extraido\n
    -> handler H_janela - uma referencia a janela criada pelo pySimpleGUI\n
    <- void return - essa função não tem um valor de retorno
    """
    origem = os.getcwd() + f"/escaneado/pagina_{pg_numero}.txt"
    if not os.path.exists(origem):
        fazer_log(H_janela,f"O arquivo {origem} , não foi localizado")
        return

    #se a tradução já existir
    #verifica se quer carregar ou criar novamente
    destino = os.getcwd() + f"/traduzido/pagina_{pg_numero}.txt"
    if os.path.exists(destino):
        questao = sg.popup_yes_no('O texto traduzido dessa página já existe.', 'Clique em [Yes] se desejar criar novamente.')
        if questao == 'No':
          try:
              traduzida = open(destino,'r')
              texto = traduzida.read()
              H_janela[ML_TRADUZIDA](texto)
              
              original = open(origem,'r')
              texto = original.read()
              H_janela[ML_ORIGINAL](texto)
              fazer_log(H_janela,f"Texto traduzido da pagina_{pg_numero}, já existe. Ignorando...")
          except Exception as e:
              fazer_log(H_janela,f"Ocorreu um erro ao tentar abrir o arquivo: pagina_{pg_numero}.txt\n Erro: {e}")
          finally:
              traduzida.close()
              original.close()
          return

    tradutor = Translator()
    original = open(origem,"r")
    traduzido = open(destino, "a")

    acumulador = ""
    paragrafos =[]

    for texto in original:
        acumulador += texto
        if len(acumulador) >= 512:
           paragrafos.append(acumulador)
           acumulador = ""

    if len(acumulador) > 0:
        paragrafos.append(acumulador)
        acumulador = ""

    for linha in paragrafos:
        tentativas = 0
        while tentativas <= 2:
            try:
                resultado = tradutor.translate(linha, dest="pt").text
                #a string retornada pelo google deve ser verificada
                #ele contém um bug que faz gerar erro na instrução write
                #https://www.fileformat.info/info/unicode/char/200b/index.htm
                filtrada = resultado.replace('\u200b', '')
                traduzido.write(filtrada)
                
                sg.cprint_set_output_destination(H_janela, ML_TRADUZIDA)
                sg.cprint(filtrada)
                
                sg.cprint_set_output_destination(H_janela, ML_ORIGINAL)
                sg.cprint(linha)
                H_janela.refresh()
                sleep(randint(2, 3))
                break
            except Exception as e:
                fazer_log(H_janela,f"Erro traduzindo a página {pg_numero}, tamanho do texto:{len(linha)}\nTexto:{linha}\nErro: {e}", 'red')
                fazer_log(H_janela,f'Erro ocorrido: {exc_info()[0]}', 'red')
                tentativas +=1
                sleep(randint(3, 5))
    
    original.close()
    traduzido.close()
    fazer_log(H_janela,f"Fim da tradução da página {pg_numero}...", 'green')
# ---------------------------------fim funções responsaveis pela tradução ---------------------------------


#função para habilitar/desabilitar os botões de comando da janela principal
def desabilitar_botoes(H_janela, estado=False):
    """
    Habilita ou desabilita os botões de comando até o termino do processamento\n
    -> handler H_janela - referencia a janela criada pelo pySimpleGUI\n
    -> bool estado - Quando True desabilita os botões\n
    <- void retorno - essa função não tem um valor de retorno
    """
    H_janela['Salvar'].update(disabled=estado)
    H_janela['Traduzir'].update(disabled=estado)
    H_janela['Limpar'].update(disabled=estado)
    H_janela['Sair'].update(disabled=estado)
    H_janela.refresh()


#-----------------------------cria a janela secundaria que mostra a imagem do pdf -------------------------
def janela_mostrar_pdf_imagem(pg_numero=None):
    """
    Cria uma nova janela no para mostrar a imagem\n
    da pagina extraida do pdf
    """
    #theme = sg.user_settings_get_entry('-theme-')
    sg.theme('Dark')
    
    PAGINA_ATUAL = 0

    coluna = [[sg.Image(key='-IMAGEM-', expand_x=True, expand_y=True)]]
    layout = [
        [sg.Button('- Zoom', key='-ZOOMMENOS-'), sg.Button('+ Zoom', key='-ZOOMMAIS-'), 
        sg.Text('Pagina:'), sg.Input(size=(10, 1), enable_events=True, key='-PAGINA-'),
        sg.Button('Anterior', key='-RETROCEDER-'), sg.Button('Proxima',key='-AVANCAR-'),
        sg.Button('Fechar', key='-FECHARIMAGEM-')],
        [sg.Column(coluna, size=(800,800), scrollable=True, key='-COLUNA-')],
        ]

    window = sg.Window('Imagem da Pagina', layout, icon=icon, size=(820, 900), resizable=True, finalize=True)

    #pega a ultima pagina aberta, caso o numero da pagina nao seja informado
    if pg_numero == None:
        pagina = get_configuracoes_ini(H_janela=window)
        if pagina != None:
            try:
                PAGINA_ATUAL = int(pagina)
            except:
                PAGINA_ATUAL = 0
            finally:
                window['-PAGINA-'](PAGINA_ATUAL)
    else:
        PAGINA_ATUAL = pg_numero
        window['-PAGINA-'](PAGINA_ATUAL)

    #se existir carrega a imagem
    origem = os.getcwd() + f"/imagens/pagina_{PAGINA_ATUAL}.jpg"
    if os.path.exists(origem):
        try:
            tamanho = (800,800)
            im = Image.open(origem)
            im.thumbnail(tamanho)
            bio = io.BytesIO()
            im.save(bio, format='PNG')
            window['-IMAGEM-'].update(data=bio.getvalue())
        except:
            print(f"Ocorreu um erro lendo arquivo pagina_{PAGINA_ATUAL}.jpg")
            print(f'Erro ocorrido: {exc_info()[0]}')
    else:
        print("imagem nao encontrada")

    dimencao_x = 800
    dimencao_y = 800
    while True:
        event, values = window.read(timeout=250)
        if event == "-FECHARIMAGEM-" or event == sg.WIN_CLOSED:
            break

        elif event == "-RETROCEDER-":
            if PAGINA_ATUAL >= 1: PAGINA_ATUAL -= 1
            origem = os.getcwd() + f"/imagens/pagina_{PAGINA_ATUAL}.jpg"
            if os.path.exists(origem):
                try:
                    tamanho = (dimencao_x,dimencao_y)
                    im = Image.open(origem)
                    im.thumbnail(tamanho)
                    bio = io.BytesIO()
                    im.save(bio, format='PNG')
                    window['-IMAGEM-'].update(data=bio.getvalue())
                    window['-PAGINA-'](PAGINA_ATUAL)
                except:
                    print(f'Erro ocorrido: {exc_info()[0]}')
        
        elif event == "-AVANCAR-":
            PAGINA_ATUAL += 1
            origem = os.getcwd() + f"/imagens/pagina_{PAGINA_ATUAL}.jpg"
            if os.path.exists(origem):
                try:
                    tamanho = (dimencao_x,dimencao_y)
                    im = Image.open(origem)
                    im.thumbnail(tamanho)
                    bio = io.BytesIO()
                    im.save(bio, format='PNG')
                    window['-IMAGEM-'].update(data=bio.getvalue())
                    window['-PAGINA-'](PAGINA_ATUAL)
                except:
                    print(f'Erro ocorrido: {exc_info()[0]}')

        elif event == "-ZOOMMAIS-":
            origem = os.getcwd() + f"/imagens/pagina_{PAGINA_ATUAL}.jpg"
            if os.path.exists(origem):
                try:
                    dimencao_x += 50
                    dimencao_y += 50
                    tamanho = (dimencao_x,dimencao_y)
                    im = Image.open(origem)
                    im.thumbnail(tamanho)
                    bio = io.BytesIO()
                    im.save(bio, format='PNG')
                    window['-IMAGEM-'].update(data=bio.getvalue())
                    window['-PAGINA-'](PAGINA_ATUAL)
                    window.refresh()
                except:
                    print(f'Erro ocorrido: {exc_info()[0]}')
        
        elif event == "-ZOOMMENOS-":
            origem = os.getcwd() + f"/imagens/pagina_{PAGINA_ATUAL}.jpg"
            if os.path.exists(origem):
                try:
                    dimencao_x -= 50
                    dimencao_y -= 50
                    tamanho = (dimencao_x,dimencao_y)
                    im = Image.open(origem)
                    im.thumbnail(tamanho)
                    bio = io.BytesIO()
                    im.save(bio, format='PNG')
                    window['-IMAGEM-'].update(data=bio.getvalue())
                    window['-PAGINA-'](PAGINA_ATUAL)
                    window.refresh()
                except:
                    print(f'Erro ocorrido: {exc_info()[0]}')

    window.close()

#player para tocar os arquivos mp3
def player_de_traducoes(pg_numero):
    """
    Abre uma nova janela com um player para\n
    reproduzir o mp3 referente a página selecionada\n
    -> int pg_numero - Numero da pagina a ser reproduzida.\n
    <- void return - Essa função não retorna valores
    """
    sg.theme('Dark')
    
    coluna = [
       [sg.Text('Tocando:', font='Any 10', key='-TOCANDO_NUM-')],
       [sg.ReadButton(button_text='', image_filename='png/Play.png', button_color=sg.TRANSPARENT_BUTTON,
            image_size=(50, 50), image_subsample=2, border_width=0, tooltip=' Tocar ',key='-Tocar-'),
          sg.ReadButton(button_text='', image_filename='png/Pause.png', button_color=sg.TRANSPARENT_BUTTON,
            image_size=(50, 50), image_subsample=2, border_width=0, tooltip=' Pausar ', key='-Pausar-'),
          sg.ReadButton(button_text='', image_filename='png/Stop.png', button_color=sg.TRANSPARENT_BUTTON,
            image_size=(50, 50), image_subsample=2, border_width=0, tooltip=' Parar ',key='-Parar-')],
       [sg.Slider(orientation ='horizontal', key='-VOLUME-', range=(1,100), default_value=50, disable_number_display=True, enable_events=True)],
       [sg.T('Volume 50%', key='-VOLUME_TXT-', font='Any 8')],
    ]

    layout = [[sg.vtop(sg.Column(coluna, element_justification='c'))]]

    window = sg.Window('Player', layout, icon=icon, size=(200, 160), finalize=True)

    mp3 = f"{os.getcwd()}/mp3/pagina_{pg_numero}.mp3"
    player = AudioPlayer(mp3)
    estado = 0
    while True:
        event, values = window.read(timeout=250)
        if event == sg.WIN_CLOSED:
            if estado > 0: player.stop()
            break
        elif event == '-Tocar-':
            if estado == 0:
                player.volume = 50
                player.play(block=False)
            elif estado == 2:
                player.resume()
            estado=1
            window['-TOCANDO_NUM-'](f'Tocando: pagina_{pg_numero}.mp3')

        elif event == '-Pausar-':
            if estado == 1:
                player.pause()
                estado = 2
                window['-TOCANDO_NUM-'](f'Pausado: pagina_{pg_numero}.mp3')
            elif estado == 2:
                player.resume()
                estado = 1
                window['-TOCANDO_NUM-'](f'Tocando: pagina_{pg_numero}.mp3')

        elif event == '-Parar-':
           player.stop() 
           break

        elif event == "-VOLUME-":
            valor = int(values['-VOLUME-'])
            window['-VOLUME_TXT-'](f'Volume {valor}%')
            player.volume = valor

    #remove qualquer referencia
    if player != None:
        del player

    window.close()

#essa função irá unir as partes .mp3 geradas pela
#função converter_texto_em_fala, criando um único .mp3
#para a pagina informada. exemplo de saida: pagina_10.mp3
def unir_partes_mp3(pg_numero):
    """
    Cria um único .mp3 com as partes pertencentes a mesma página\n
    -> int pg_numero - numero da página\n
    <- bool return - retorna True se o arquivo já existir ou\n
    se for gerado com sucesso, e False nos outros casos.
    """
    #se o arquivo já existir, então não precisa fazer a concatenação
    mp3_final = f'{os.getcwd()}/mp3/pagina_{pg_numero}.mp3'
    if os.path.exists(mp3_final):
        return True

    #quando uma lista é vazia, é atribuido um valor False
    mp3_lista = glob.glob(f'{os.getcwd()}/mp3/pagina_{pg_numero}_parte_*.mp3')
    if not mp3_lista:
        sg.popup(f"Não foram encontrados arquivo mp3 referentes a página {pg_numero}")
        return False
    else:
        msg = f"Foram encontrados {len(mp3_lista)} arquivos mp3, referentes a página {pg_numero}\n"
        msg += f"Por favor aguarde a criação do arquivo final: pagina_{pg_numero}.mp3"
        sg.popup(msg, auto_close=True, auto_close_duration=5)

    #caso exista 10 ou mais partes, a função glob irá retornar
    #a lista de forma desordenada, exemplo parte_1, parte_10, parte_11, parte_2, etc...
    
    #repare algo interessante no python, uma função dentro de outra!!!
    #def ordena_certo(p):
    #    return len(p)

    #faz a ordenação correta, usando uma função auxiliar
    #tanto a função mostrada acima quanto a função anonima funcionam corretamente
    mp3_lista.sort(key=lambda p: len(p))

    #cria um segmento de audio silencioso de 250ms entre uma parte e outra
    silencio = AudioSegment.silent(duration=250)
    pagina_mp3 = silencio
    try:
        for audiosF in mp3_lista:
            sg.popup_animated('png/aguarde.gif', f'Criando arquivo: pagina_{pg_numero}.mp3')
            pagina_mp3 += AudioSegment.from_mp3(audiosF) + silencio

        pagina_mp3.export(mp3_final)
        sg.popup_animated(None)
        return True
    except Exception as e:
        sg.popup_animated(None)
        sg.popup(f"Ocorreu o seguinte erro: {str(e)}")
    
    sg.popup_animated(None)
    return False

#converte o texto do arquivo traduzido em voz
#aqui é usado um serviço online do google, devido
#a isso o texto é enviado em pequenas partes
#isso irá gerar 1 .mp3 para cada parte, depois de todas
#as partes serem geradas, elas serão unidas pela função
#unir_partes_mp3.
def converter_texto_em_fala(H_janela, pg_numero):
    
    #verifica se a pagina já foi convertida em audio
    #em caso positivo, chama o player
    mp3_final = f'{os.getcwd()}/mp3/pagina_{pg_numero}.mp3'
    if os.path.exists(mp3_final):
        player_de_traducoes(pg_numero) #chama o player
        return

    origem = os.getcwd() + f"/traduzido/pagina_{pg_numero}.txt"
    if not os.path.exists(origem):
        sg.Popup(f"O arquivo {origem} , não foi localizado")
        return

    original = open(origem,"r")
    
    acumulador = ""
    paragrafos =[]
    for texto in original:
        acumulador += texto
        if len(acumulador) >= 128:
           paragrafos.append(acumulador)
           acumulador = ""

    if len(acumulador) > 0:
        paragrafos.append(acumulador)
        acumulador = ""

    original.close()
     
    contador = 1
    for linha in paragrafos:
        sg.popup_animated('png/aguarde.gif', 'Convertendo texto em voz...')
        H_janela.refresh()
        tentativas = 0
        while tentativas <= 2:
            try:
                mp3 = os.getcwd() + f"/mp3/pagina_{pg_numero}_parte_{contador}.mp3"
                #se o arquivo já existir então não faz nada
                if os.path.exists(mp3):
                    break

                audio = gTTS(text=linha, lang="pt", slow=False)
                audio.save(mp3)
                sg.popup_animated('png/aguarde.gif', 'Convertendo texto em voz...')
                H_janela.refresh()
                sleep(randint(2, 3))
                break
            except:
                sg.popup_animated(None)
                H_janela.refresh()
                sg.popup_scrolled(f'Erro traduzindo a página {pg_numero}, tamanho do texto:{len(linha)} Texto:{linha}\nErro ocorrido: {exc_info()[0]}\nFeche essa mensagem para que o script tente novamente.',
                auto_close=True, auto_close_duration=30)
                tentativas +=1
                sleep(randint(3, 5))
        
        contador += 1
    
    sg.popup_animated(None)
    sg.Popup(f"Fim da conversão da página {pg_numero}\nA leitura será iniciada em 3 segundos", auto_close=True, auto_close_duration=3)
    H_janela.refresh()

    #tenta unir as partes .mp3 caso existam
    if unir_partes_mp3(pg_numero):
        player_de_traducoes(pg_numero) #chama o player

#------------------------------------ teste usando thread para text-to-speech ----------------------
THREAD_KEY = '-THREAD-'
DL_START_KEY = '-START DOWNLOAD-'
DL_COUNT_KEY = '-COUNT-'
DL_END_KEY = '-END DOWNLOAD-'
DL_THREAD_EXITNG = '-THREAD EXITING-'
def the_thread(window:sg.Window, pg_numero=0):
    """
    The thread that communicates with the application through the window's events.
    Simulates downloading a random number of chinks from 50 to 100-
    """
    
    max_value = 100
    window.write_event_value((THREAD_KEY, DL_START_KEY), max_value)
    
    #verifica se a pagina já foi convertida em audio
    #em caso positivo, chama o player
    mp3_final = f'{os.getcwd()}/mp3/pagina_{pg_numero}.mp3'
    if os.path.exists(mp3_final):
        sleep(1)
        window.write_event_value((THREAD_KEY, DL_COUNT_KEY), max_value)
        sleep(2)
        window.write_event_value((THREAD_KEY, DL_END_KEY), max_value)
        return

    origem = os.getcwd() + f"/traduzido/pagina_{pg_numero}.txt"
    if not os.path.exists(origem):
        sleep(1)
        window.write_event_value((THREAD_KEY, DL_COUNT_KEY), max_value)
        sleep(2)      
        window.write_event_value((THREAD_KEY, DL_END_KEY), max_value)
        return

    original = open(origem,"r")
    acumulador = ""
    paragrafos =[]
    for texto in original:
        acumulador += texto
        if len(acumulador) >= 128:
           paragrafos.append(acumulador)
           acumulador = ""

    if len(acumulador) > 0:
        paragrafos.append(acumulador)
        acumulador = ""
    original.close()

    #porcentagem = (100 / len(paragrafos))
    contador = 1
    window.write_event_value((THREAD_KEY, DL_START_KEY), len(paragrafos))
    for linha in paragrafos:
        tentativas = 0
        while tentativas <= 2:
            try:
                mp3 = os.getcwd() + f"/mp3/pagina_{pg_numero}_parte_{contador}.mp3"
                if os.path.exists(mp3): break
                audio = gTTS(text=linha, lang="pt", slow=False)
                audio.save(mp3)
                #max_value = int(contador * porcentagem)
                window.write_event_value((THREAD_KEY, DL_COUNT_KEY), contador)
                sleep(randint(2, 3))
                break
            except Exception as e:
                print(f'Erro convertendo arquivo: {mp3}\nErro: {e}')
                try:
                  if os.path.exists(mp3):
                    os.remove(mp3)
                except:
                  print(f'Erro removendo o arquivo: {mp3}')

                tentativas +=1
                sleep(randint(3, 5))        
        contador += 1
    
    window.write_event_value((THREAD_KEY, DL_END_KEY), max_value)



def janela_converte_texto_fala_thread(pg_numero):
    layout = [[sg.Text('Click em Iniciar para começar a conversão')],
              [sg.ProgressBar(100, 'h', size=(30,20), k='-PROGRESS-', expand_x=True)],
              [sg.Text(key='-STATUS-')],
              [sg.Button('Iniciar',key='-TH_INICIAR-'), sg.Button('Sair', key='-TH_SAIR-')]
            ]

    window = sg.Window('Converter texto em voz', layout, finalize=True, relative_location=(0, -300))
    downloading, max_value = False, 0
    while True:
        event, values = window.read()
        
        if event == sg.WIN_CLOSED or event == '-TH_SAIR-':
            if not downloading: break

        if event == '-TH_INICIAR-' and not downloading:
            window.start_thread(lambda: the_thread(window,pg_numero), (THREAD_KEY, DL_THREAD_EXITNG))
        #eventos recebidos do thread
        elif event[0] == THREAD_KEY:
            if event[1] == DL_START_KEY:
                max_value = values[event]
                downloading = True
                window['-STATUS-'].update('Iniciando a conversão')
                sg.one_line_progress_meter(f'Baixando {max_value} audio', 0, max_value, 1, f'Baixando {max_value} audio', )
                window['-PROGRESS-'].update(0, max_value)
            elif event[1] == DL_COUNT_KEY:
                sg.one_line_progress_meter(f'Baixando {max_value} audio', values[event]+1, max_value, 1, f'Baixando {max_value} audio')
                window['-STATUS-'].update(f'Convertendo... {values[event]}')
                window['-PROGRESS-'].update(values[event]+1, max_value)
            elif event[1] == DL_END_KEY:
                downloading = False
                window['-STATUS-'].update('Conversão terminada')
            elif event[1] == DL_THREAD_EXITNG:
                sg.one_line_progress_meter_cancel()
                window['-STATUS-'].update('Saindo')
                break

    window.close()
#------------------------------------ teste usando thread para text-to-speech ----------------------


#-----------------------------cria a janela secundaria para leiturado do pdf ---------------------------------
def janela_leitura_pdf(pg_numero = None):
    """
    Cria uma nova janela no estilo modal\npara mostrar as páginas traduzidas\n
    """
    PAGINA_ATUAL = 0
    
    sg.theme('Dark')
    layout = [
       [sg.Text('Informe o numero da pagina:'), sg.Input(size=(10, 1), enable_events=True, key='-PAGINA-'),
       sg.Button('Anterior'), sg.Button('Proximo'), sg.Button('Imagem', key='-ESCANEADA-'),
       sg.Button('Falar'), sg.Button('Fechar'), sg.Text('Tradução', font='Any 20', key='-INFO-')],
       [sg.Multiline(size=(220, 80), font=('Any', 12, 'bold'), write_only=True, key='-ML_LEITURA-')],
    ]

    window = sg.Window('Leitura', layout, icon=icon, size=(1000, 800), resizable=True, finalize=True)
    
    #pega a ultima pagina aberta
    pagina = get_configuracoes_ini(H_janela=window)
    if pagina != None:
        try:
            PAGINA_ATUAL = int(pagina)
        except:
            PAGINA_ATUAL = 0
    
    #caso não exista a ultima pagina lida, verifica a ultima traduzida
    if PAGINA_ATUAL == 0 and pg_numero != None:
        PAGINA_ATUAL = pg_numero

    window['-PAGINA-'](PAGINA_ATUAL)

    #se existir carrega a ultima pagina aberta
    origem = os.getcwd() + f"/traduzido/pagina_{PAGINA_ATUAL}.txt"
    if os.path.exists(origem):
        window['-ML_LEITURA-']('')
        window['-INFO-']('Tradução da página: ' + str(PAGINA_ATUAL))
        try:
            traduzido = open(origem, "r")
            texto = traduzido.read()
            window['-ML_LEITURA-'](texto)
        except Exception as e:
            mostra_erro(f"Ocorreu um erro lendo arquivo pagina_{PAGINA_ATUAL}.txt\n Erro: {e}")
        finally:
            traduzido.close()
    else:
        window['-ML_LEITURA-']('')
        window['-ML_LEITURA-'](f'Página {PAGINA_ATUAL}, não encontrada.')

    #mantém a janela em loop
    while True:
        event, values = window.read(timeout=250)
        if event == "Fechar" or event == sg.WIN_CLOSED:
            set_configuracao_ini(window, pg_vista=PAGINA_ATUAL)
            break
        
        elif event == '-ESCANEADA-':
            janela_mostrar_pdf_imagem(PAGINA_ATUAL)
        
        elif event == 'Falar':
            #desabilita os botões enquanto processa
            window['Anterior'].update(disabled=True)
            window['Proximo'].update(disabled=True)
            window['-ESCANEADA-'].update(disabled=True)
            window['Falar'].update(disabled=True)
            window['Fechar'].update(disabled=True)
            window.refresh()
            
            mp3_final = f'{os.getcwd()}/mp3/pagina_{pg_numero}.mp3'
            if os.path.exists(mp3_final): #chama o player
              player_de_traducoes(pg_numero)
            else: #chama a janela de conversão
              janela_converte_texto_fala_thread(PAGINA_ATUAL)
              if unir_partes_mp3(PAGINA_ATUAL):
                player_de_traducoes(PAGINA_ATUAL)

            #reabilita os botões ao termino
            window['Anterior'].update(disabled=False)
            window['Proximo'].update(disabled=False)
            window['-ESCANEADA-'].update(disabled=False)
            window['Falar'].update(disabled=False)
            window['Fechar'].update(disabled=False)
            window.refresh()

        elif event == 'Anterior':
            if PAGINA_ATUAL >= 1:
                PAGINA_ATUAL -= 1
                origem = os.getcwd() + f"/traduzido/pagina_{PAGINA_ATUAL}.txt"
                if os.path.exists(origem):
                    window['-ML_LEITURA-']('')
                    window['-INFO-']('Tradução da página: ' + str(PAGINA_ATUAL))
                    try:
                        traduzido = open(origem, "r")
                        texto = traduzido.read()
                        window['-ML_LEITURA-'](texto)
                    except Exception as e:
                        mostra_erro(f"Ocorreu um erro lendo arquivo pagina_{PAGINA_ATUAL}.txt\nErro: {e}")
                    finally:
                        traduzido.close()
                else:
                    window['-ML_LEITURA-']('')
                    window['-ML_LEITURA-'](f'Página {PAGINA_ATUAL}, não encontrada.')

                window['-PAGINA-'](PAGINA_ATUAL)
                
        elif event == 'Proximo':
            PAGINA_ATUAL += 1
            origem = os.getcwd() + f"/traduzido/pagina_{PAGINA_ATUAL}.txt"
            if os.path.exists(origem):
                window['-ML_LEITURA-']('')
                window['-INFO-']('Tradução da página: ' + str(PAGINA_ATUAL))
                try:
                    traduzido = open(origem, "r")
                    texto = traduzido.read()
                    window['-ML_LEITURA-'](texto)
                except Exception as e:
                    mostra_erro(f"Ocorreu um erro lendo arquivo pagina_{PAGINA_ATUAL}.txt\nErro: {e}")
                finally:
                    traduzido.close()    
            else:
               window['-ML_LEITURA-']('')
               window['-ML_LEITURA-'](f'Página {PAGINA_ATUAL}, não encontrada.')
            
            window['-PAGINA-'](PAGINA_ATUAL)
            
        elif event == '-PAGINA-':
            pagina_informada = values["-PAGINA-"]
            try:
                if len(pagina_informada) > 0:
                    PAGINA_ATUAL = int(pagina_informada)
            except:
                window['-PAGINA-'](PAGINA_ATUAL)
        
    window.close()

# --------------------------------- Cria a janela principal ---------------------------------
def janela_inicial():
    """
    Cria a janela inicial da aplicação\n
    <- handler return - retorna uma referencia a janela criada
    """
    theme = sg.user_settings_get_entry('-theme-')
    sg.theme(theme)

    #tooltips para os botões
    dicas_traduzir = " Inicia o processo de tradução da página informada "
    dicas_Limpar = " Limpa todos os campos "
    dicas_sair = " Fecha o script "
    dicas_browser = " Abre uma janela para localizar\no arquivo pdf desejado "
    dicas_salvar = " Salva as alterações realizadas nesse campo "
    dicas_aumentar = " Aumenta o tamanho da fonte "
    dicas_diminuir = " Diminue o tamanho da fonte "
    dicas_ler = " Abre uma nova janela\npara lêr as páginas traduzidas "
    dicas_imagem= " Mostra a imagem capturada da página "
    
    txt_descricao = "Descrição:\nSelecione o arquivo pdf atravez do botão [Browser]\n"
    txt_descricao += "No campo [Informe o número da página] digite o número\n"
    txt_descricao += "da página a ser traduzida, depois clique em [Traduzir]\n"
    txt_descricao += "Ao término da tradução, você pode corrigir o texto e clicar em [Salvar]"

    
    #o layout será dividido em duas colunas
    left_col = [
        [sg.Button(' + ', key='-FONTE1-', tooltip=dicas_aumentar), sg.Button(' - ', key='-FONTE2-', tooltip=dicas_diminuir),
        sg.Text('Tradução', font='Any 18'), sg.Button('Salvar', tooltip=dicas_salvar),],
        [sg.Multiline(size=(100, 40), write_only=True, key=ML_TRADUZIDA)],
        [sg.Text('Informe o numero da pagina:'), sg.Input(size=(25, 1), enable_events=True, key='-PAGINA-'),
        sg.Button('Traduzir',tooltip=dicas_traduzir), sg.Button('Limpar', tooltip=dicas_Limpar),
        sg.Button('Ler', tooltip=dicas_ler), sg.Button('Imagem', key='-ESCANEADA0-',tooltip=dicas_imagem), sg.Button('Sair', tooltip=dicas_sair)],
    ]

    right_col = [
        [sg.Text('Original', font='Any 18')],
        [sg.Multiline(size=(100, 40), write_only=True, key=ML_ORIGINAL)],
        [sg.Input(key='-ARQUIVO_PDF-'), sg.FileBrowse(file_types=(("Arquivos PDF", "*.pdf"), ("Todos os arquivos", "*.*")),tooltip=dicas_browser)],
    ]

    # ----- layout final -----
    layout = [[sg.vtop(sg.Column(left_col, element_justification='c')), sg.VSeperator(), sg.vtop(sg.Column(right_col, element_justification='c'))],
              [sg.HorizontalSeparator()],
              [sg.Multiline(size=(100, 20), write_only=True, key=ML_LOG, reroute_stdout=True, echo_stdout_stderr=True),
              sg.Text(txt_descricao, font=('Any', 12, 'bold' ))],
              ]

    #cria a janela e configura a saida do log
    window = sg.Window('Tradução de livros', layout, icon=icon, size=(1500, 900), resizable=True, finalize=True)
    return window

def criar_pastas():
    """
    Verifica se as 4 pastas usadas pelo script existem
    caso não existam então serão criadas
    """
    pasta_trabalho = os.getcwd()
    pasta_mp3 = f"{pasta_trabalho}/mp3"
    pasta_traduzido = f"{pasta_trabalho}/traduzido"
    pasta_escaneado = f"{pasta_trabalho}/escaneado"
    pasta_imagens = f"{pasta_trabalho}/imagens"

    try:
        if not os.path.exists(pasta_mp3): os.makedirs(pasta_mp3)
        if not os.path.exists(pasta_traduzido): os.makedirs(pasta_traduzido)
        if not os.path.exists(pasta_escaneado): os.makedirs(pasta_escaneado)
        if not os.path.exists(pasta_imagens): os.makedirs(pasta_imagens)
    except Exception as e:
        mostra_erro(f'Erro criando as pastas, erro: {e}')

# --------------------------------- Função Main ----------------------------------------------------------
def main():
    window = janela_inicial()
    processando = False
    pagina_numero = 0

    #usado somente para demonstrar o uso da palavra reservada: global
    ML_FONTE_TAMANHO = 10

    #verifica se as pasta existem, e cria caso necessario
    criar_pastas()

    #carrega as configurações se existirem
    configuracao = get_configuracoes_ini(sessao=1)
    if configuracao != None:
        window["-PAGINA-"](configuracao)

    try:
        pagina_numero = int(configuracao)
    except:
        pagina_numero = 0

    configuracao = get_configuracoes_ini(sessao=2)
    if configuracao != None:
        window["-ARQUIVO_PDF-"](configuracao)
        
    while True:
        event, values = window.read(timeout=250)
        if event == sg.WINDOW_CLOSED or event == 'Sair':
            if not processando:
                break

        if event == "-FONTE1-":
            if ML_FONTE_TAMANHO < 24: ML_FONTE_TAMANHO += 2
            window[ML_TRADUZIDA].update(font=('Any', ML_FONTE_TAMANHO, 'bold'))
            window[ML_ORIGINAL].update(font=('Any', ML_FONTE_TAMANHO, 'bold'))

        elif event == "-FONTE2-":
            if ML_FONTE_TAMANHO > 10: ML_FONTE_TAMANHO -= 2
            window[ML_TRADUZIDA].update(font=('Any', ML_FONTE_TAMANHO, 'bold'))
            window[ML_ORIGINAL].update(font=('Any', ML_FONTE_TAMANHO, 'bold'))

        elif event == "Salvar":
            pagina_informada = values["-PAGINA-"]
            try:
               pagina_numero = int(pagina_informada)
            except:
               fazer_log(window,'O valor informado no campo página não é válido', 'red')
               continue

            texto_final = window[ML_TRADUZIDA].get()
            if texto_final == "":
                fazer_log(window,f'O campo traduzir não deve estar vazio', 'red')
                continue

            try:
                destino = os.getcwd() + f"/traduzido/pagina_{pagina_numero}.txt"
                corrigido = open(destino, "w")
                corrigido.write(texto_final)
                fazer_log(window,f'Página: {pagina_numero}, salva com sucesso', 'green')
            except:
                fazer_log(window,f'Erro tentando salvar a página: {pagina_numero}', 'red')    
            finally:
                corrigido.close()

        elif event == 'Traduzir':
            pagina_informada = values["-PAGINA-"]
            try:
               pagina_numero = int(pagina_informada)
               fazer_log(window,f'Iniciando a tradução da página {pagina_numero}')
            except:
               fazer_log(window,'O valor informado no campo página não é válido', 'red')
               continue

            #limpa os multi-textos antes de iniciar uma nova tradução
            window[ML_TRADUZIDA]('')
            window[ML_ORIGINAL]('')

            #configura a flag indicando o inicio do processo    
            processando = True
            desabilitar_botoes(window, True)

            if not escanear_pagina(pagina_numero, window):
                processando = False
                desabilitar_botoes(window, False)
                continue

            if not converte_para_texto(pagina_numero, window):
                processando = False
                desabilitar_botoes(window, False)                
                continue

            traduzir_texto(pagina_numero, window)
            
            processando = False
            desabilitar_botoes(window, False)
            set_configuracao_ini(arquivo_pdf=window["-ARQUIVO_PDF-"].get(), pg_traduzida=pagina_numero)

        elif event == 'Limpar':
            window[ML_LOG]('')
            window[ML_TRADUZIDA]('')
            window[ML_ORIGINAL]('')
        
        elif event == 'Ler':
           janela_leitura_pdf(pagina_numero)

        elif event == '-ESCANEADA0-':
            pagina_informada = values["-PAGINA-"]
            try:
                pagina_numero = int(pagina_informada)
                janela_mostrar_pdf_imagem(pagina_numero)   
            except:
                janela_mostrar_pdf_imagem(pg_numero=None)
            
    window.close()


if __name__ == '__main__':
    icon = b'iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAMAAAD04JH5AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAMAUExURQAAAB69LymqOSm6LSq2OTSrOjS2Ox28RjqdQC6qSiy3Riu3UTisRzirVDi1STq0UiuyYz6pYz62ZCjDNyjQPzTAOxrIQinARTXDRzXBVEWsP1ieZ0OrSUaqV0S0SkOzVFKnSVKrWlK0W0iqZUWmcEe0a1eoZ1apclW0Z1uzd2G8X2W8Z2i3dXStdnS/ZHW7dkXCTEnCWVnDbF3Gc1zUc2bGbGjId2fRbWjQfnLFbnTGeHfReXu6hWzFgWzRgXfGhn3Jk3bShHvWkd5HPNhYJ9RWPtRbPdxVOtlbM9xdPM5iPNRjO9VsMtNoOttiPOFVNOVUPeNZNOJbPelVPelZN+pcO/ZYPeNjPeFqPOlgNOpiPfBkO8xcR85ZUtZOUNJXQdNcQtNcTNpTRdxVT9xdQ95cSdlbUsBgR8xkRctkTc1oQ81pS8tmVMtxTsx3XtVjQdRjStRoQtNqStxiRNtjSdxpQ9toS9NkU9diWdFqUtVsW9xiU9xlXN5uVtZzWsptZ8Z3Y8p2ddBuY9duat1qY9Nvcdh3Z+VOQ+NUROJcQ+NcSutTROlcQ+pdSuhdVPJcQ/FbS/heQvZbVuFhReJjSeJpRORpTOpiRepiS+toTeVlU/RhRfJhUuZnYeBvaeR4aoPCfN+Hb9eHfNmQfeaIbOKIeOWSefaHbP+Ia/CMffCSePigeoTHhovJmIjWiYXXl5HMnpbYmY3bp4fes5PHoJnapJzUspDhnozjpo3lspnjqaLTm6HOsaPYp7XOuLbduajkqavpuLTpt7f2uKvbwbLYw7nmx7f1ybjw1tqIhtiThtiSkNasnNuimeSLhOWPkOWThuicl/mdiPKbku6fouWjl+Oinuaom+ynl+yjmuqpl+qqm/OllfOlmPSqnf6mkvqhneekoPOho8buuNPtvtbd08bpyMro1cT2ysj109XozNXo2NHzydT52M/45tvs4tj8497+8eD6y+b82+bq6Of+5+n+9fnq7f/p//b96fv7+gAAAAAAAAAAAAAAAAAAAFSfM6AAAAEAdFJOU////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////wBT9wclAAAACXBIWXMAAA7DAAAOwwHHb6hkAAAMlUlEQVR4Xu2Zf5gbRRnHtd5Fm+Z2FUQOuWQplXI+oAVqA0RrAKUlRGINlkCpei2b2EI1187eFUitBfFgc0nah5m7pFsFnvJD1FIseoDFk1/agj+wpz5gBX8geu31ODmtqb39J76zO5vb/Lzsnjw8Pt7nLpfZmcnMd99533dmc28rvMXMCJgRMCNgRsCMgP9tAQdv23jDTYm72JU9piPg5U29W8OB1O2Jl1mFHaYh4I+dS7NAbkeg8yCrsoF9AS9Ge6++Ik6k4BV9qVW/ZJXWsS3gwf4ORDAWZYQwRsqDrNoydgUc7EcwP8KEEEyQiJQh1mAVmwJeIaKI+5EoUiMggpbYVmBPwFDmk0QiWBaxjCmEoCsz9hTYE/D8J65FGIl0AegawGqQCE7YigWbS9DTK4LvYSwDhMjgiShIEnZsYNcJt9DVJ7Iowy8toQ4cxHZWwa6AAiEwM5HJdpm6AZGVDhTptaHAsoDvdr6gF76WvDqckqT1KJ3GCsnIEJNItJ4PrAoYikc3MgWbU6l+HN+AUql0HEFM2MsHFgUMZe7oiq86oF8kRImaPxtAUpdoNx9YEzCUuTIb6pNjTMHdq6Srli3PdgWxGKYxYScfWBJwMIEjIo5Eigq23JpQYitFBefAIe3lAysChhIkiNbnwsFcb2wnqwNe+OYd27YHtZiwkQ8sCBjKQKh3EEgAKEfE+1kt5bZLUdBuPmhcAKx/BHUoadKZjl8euqqXxYLG5kDKbj5oWMCDCpJgkfXNB0DdzA8oQ6uWs2rYnazlg0YFHFRg/4WtH8ysE+k03+W6LKuGPtbyQYMChjIQ4jAwmwWIJFiTxrrPsGrAWj5oTMBQZhlE2KT9gbDC2jTWrWDVOhbyQUMCaPzDmHTg4hKs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'
    main()
