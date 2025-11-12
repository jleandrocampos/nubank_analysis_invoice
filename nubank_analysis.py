import re
import pandas as pd
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

CATEGORIAS_PALAVRAS_CHAVE = {
    'Supermercado': ['supermercado', 'mateus', 'mix', 'atacadao'],
    'Combustível': ['posto', 'combustível', 'gasolina', 'shell', 'ipiranga'],
    'Farmácia': ['drogaria', 'farmácia', 'paguemenos', 'drogasil'],
    'Alimentação': ['pizzaria', 'espeto', 'restaurante', 'ifood', 'lanche', 'mcdonalds', 'burger king'],
    'Serviços/Assinaturas': ['paypal', 'contabo', 'aws', 'google', 'uber', '99', 'spotify', 'netflix'],
    'Transporte': ['uber', '99', 'passagem', 'onibus'],
    'Casa': ['energia', 'agua', 'aluguel', 'internet']
}

def categorizar_transacao(titulo):
    """Categoriza uma transação com base no seu título."""
    if pd.isna(titulo):
        return 'Outros'
    titulo_lower = str(titulo).lower()
    
    for categoria, palavras in CATEGORIAS_PALAVRAS_CHAVE.items():
        if any(palavra in titulo_lower for palavra in palavras):
            return categoria
            
    return 'Outros' 

def formatar_valor(valor, com_sinal=False):
    """Formata valor para padrão brasileiro R$"""
    sinal = ''
    if com_sinal:
        sinal = '+' if valor >= 0 else '-'
    
    valor_fmt = f"{abs(valor):,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')
    return f"{sinal} R$ {valor_fmt}"

def processar_arquivos_nubank(caminho_pasta):
    """Processa todos os arquivos CSV do Nubank em uma pasta."""
    pasta = Path(caminho_pasta)
    arquivos_csv = list(pasta.glob("Nubank_*.csv"))
    
    if not arquivos_csv:
        print(f"Nenhum arquivo CSV 'Nubank_*.csv' encontrado na pasta: {pasta.resolve()}")
        return None
    
    dfs = []
    print(f"Encontrados {len(arquivos_csv)} arquivos. Lendo...")
    
    for arquivo in arquivos_csv:
        try:
            df = pd.read_csv(arquivo)
            colunas_essenciais = ['date', 'title', 'amount']
            if not all(col in df.columns for col in colunas_essenciais):
                print(f"  Erro: Arquivo {arquivo.name} não possui colunas esperadas ({', '.join(colunas_essenciais)})")
                continue
            df['arquivo_origem'] = arquivo.name
            dfs.append(df)
            print(f"  ✓ Arquivo lido: {arquivo.name} ({len(df)} transações)")
        except Exception as e:
            print(f"  ✗ Erro ao ler {arquivo.name}: {e}")
    
    if not dfs:
        print("Nenhum arquivo pôde ser lido.")
        return None
        
    df_completo = pd.concat(dfs, ignore_index=True)
    return df_completo

def limpar_e_processar_dados(df):
    """Limpa, processa e categoriza os dados do dataframe."""
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])  # Remove linhas com data inválida
    df['mes_ano'] = df['date'].dt.to_period('M')
    df['tipo'] = 'Compra'
    df.loc[df['title'].str.contains('Pagamento recebido', case=False, na=False), 'tipo'] = 'Pagamento'
    df.loc[df['title'].str.contains('IOF', case=False, na=False), 'tipo'] = 'IOF'
    df['parcelado'] = df['title'].str.contains('Parcela', case=False, na=False)
    padrao_parcela = r'Parcela (\d+)/(\d+)'
    df[['num_parcela', 'total_parcelas']] = df['title'].str.extract(padrao_parcela, flags=re.IGNORECASE)
    df['num_parcela'] = pd.to_numeric(df['num_parcela'], errors='coerce')
    df['total_parcelas'] = pd.to_numeric(df['total_parcelas'], errors='coerce')
    df['categoria'] = df['title'].apply(categorizar_transacao)
    df.loc[df['tipo'] != 'Compra', 'categoria'] = df['tipo']
    
    return df

def imprimir_resumo_console(df):
    """Imprime um resumo organizado de cada mês no console."""
    
    print("\n" + "="*60)
    print("RESUMO FINANCEIRO MENSAL (CONSOLE)")
    print("="*60)

    meses = sorted(df['mes_ano'].unique())
    
    for mes in meses:
        print(f"\n================== MÊS: {mes} ==================")
        df_mes = df[df['mes_ano'] == mes].copy()
        compras = df_mes[df_mes['tipo'] == 'Compra']
        pagamentos = df_mes[df_mes['tipo'] == 'Pagamento']
        iofs = df_mes[df_mes['tipo'] == 'IOF']
        
        total_compras = compras['amount'].sum()
        total_iofs = iofs['amount'].sum()
        total_pagamentos = pagamentos['amount'].sum()
        valor_fatura = total_compras + total_iofs
        saldo_final = total_pagamentos + valor_fatura

        print(f"\nResumo Financeiro:")
        print(f"  Valor Total da Fatura...: {formatar_valor(valor_fatura)}")
        print(f"  Pagamentos Recebidos...: {formatar_valor(total_pagamentos)}")
        
        print(f"  Saldo (Fatura - Pgto)...: {formatar_valor(saldo_final, com_sinal=True)}")

        print(f"\n🏆 Top 5 Maiores Gastos:")
        top_5_gastos = compras.nlargest(5, 'amount')
        
        if top_5_gastos.empty:
            print(f"  Nenhuma compra registrada este mês.")
        else:
            for _, row in top_5_gastos.iterrows():
                desc = str(row['title']).replace('\n', ' ')
                desc_curta = (desc[:40] + '...') if len(desc) > 40 else desc
                valor_str = formatar_valor(row['amount'])
                print(f"  {valor_str:>16} | {desc_curta}")

        print(f"\n📊 Gastos por Categoria:")
        gastos_cat = compras.groupby('categoria')['amount'].sum().sort_values(ascending=False)
        gastos_cat = gastos_cat[gastos_cat > 0]
        
        if gastos_cat.empty:
            print(f"  Nenhum gasto categorizado este mês.")
        else:
            for categoria, valor in gastos_cat.items():
                valor_str = formatar_valor(valor)
                print(f"  {valor_str:>16} | {categoria}")

def gerar_pdf_resumo(df, nome_arquivo="resumo_financeiro.pdf"):
    """Gera um relatório PDF similar ao resumo do console."""
    doc = SimpleDocTemplate(nome_arquivo, pagesize=A4,
                            rightMargin=72, leftMargin=72,
                            topMargin=72, bottomMargin=18)
    story = []
    styles = getSampleStyleSheet()
    
    titulo_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )
    
    subtitulo_style = ParagraphStyle(
        'CustomSub',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=12,
        alignment=TA_CENTER,
        textColor=colors.black
    )
    
    normal_style = styles['Normal']
    normal_style.alignment = TA_LEFT
    
    valor_style = ParagraphStyle(
        'Valor',
        parent=normal_style,
        alignment=TA_RIGHT,
        fontSize=10
    )
    
    story.append(Paragraph("RESUMO FINANCEIRO MENSAL - NUBANK", titulo_style))
    story.append(Spacer(1, 12))
    
    meses = sorted(df['mes_ano'].unique())
    
    for mes in meses:
        df_mes = df[df['mes_ano'] == mes].copy()
        
        story.append(Paragraph(f"MÊS: {mes}", subtitulo_style))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Resumo Financeiro:", styles['Heading3']))
        story.append(Spacer(1, 6))
        compras = df_mes[df_mes['tipo'] == 'Compra']
        pagamentos = df_mes[df_mes['tipo'] == 'Pagamento']
        iofs = df_mes[df_mes['tipo'] == 'IOF']
        total_compras = compras['amount'].sum()
        total_iofs = iofs['amount'].sum()
        total_pagamentos = pagamentos['amount'].sum()
        valor_fatura = total_compras + total_iofs
        saldo_final = total_pagamentos + valor_fatura
        
        dados_resumo = [
            ['Item', 'Valor'],
            ['Valor Total da Fatura', formatar_valor(valor_fatura)],
            ['Pagamentos Recebidos', formatar_valor(total_pagamentos)],
            ['Saldo (Fatura - Pgto)', formatar_valor(saldo_final, com_sinal=True)]
        ]
        tabela_resumo = Table(dados_resumo, colWidths=[2.5*inch, 1.5*inch])
        tabela_resumo.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(tabela_resumo)
        story.append(Spacer(1, 12))
        
        story.append(Paragraph("🏆 Top 5 Maiores Gastos:", styles['Heading3']))
        story.append(Spacer(1, 6))
        
        top_5_gastos = compras.nlargest(5, 'amount')
        if not top_5_gastos.empty:
            dados_top = [['Valor', 'Descrição']]
            for _, row in top_5_gastos.iterrows():
                desc = str(row['title']).replace('\n', ' ')
                desc_curta = (desc[:60] + '...') if len(desc) > 60 else desc  # Ajuste para PDF
                dados_top.append([formatar_valor(row['amount']), desc_curta])
            
            tabela_top = Table(dados_top, colWidths=[1*inch, 4.5*inch])
            tabela_top.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(tabela_top)
        else:
            story.append(Paragraph("Nenhuma compra registrada este mês.", normal_style))
        story.append(Spacer(1, 12))
        
        story.append(Paragraph("📊 Gastos por Categoria:", styles['Heading3']))
        story.append(Spacer(1, 6))
        
        gastos_cat = compras.groupby('categoria')['amount'].sum().sort_values(ascending=False)
        gastos_cat = gastos_cat[gastos_cat > 0]
        if not gastos_cat.empty:
            dados_cat = [['Valor', 'Categoria']]
            for categoria, valor in gastos_cat.items():
                dados_cat.append([formatar_valor(valor), categoria])
            
            tabela_cat = Table(dados_cat, colWidths=[1*inch, 4.5*inch])
            tabela_cat.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(tabela_cat)
        else:
            story.append(Paragraph("Nenhum gasto categorizado este mês.", normal_style))
        story.append(PageBreak())
    
    story.append(Paragraph("RESUMO GERAL DO PERÍODO", titulo_style))
    story.append(Spacer(1, 12))
    
    total_gasto = df[df['tipo'] != 'Pagamento']['amount'].sum()
    total_pago = df[df['tipo'] == 'Pagamento']['amount'].sum()
    
    dados_geral = [
        ['Item', 'Valor'],
        ['Período Analisado', f"{df['date'].min().strftime('%d/%m/%Y')} até {df['date'].max().strftime('%d/%m/%Y')}"],
        ['Total de Meses', str(df['mes_ano'].nunique())],
        ['Total de Transações', str(len(df))],
        ['Total Gasto (Compras + IOF)', formatar_valor(total_gasto)],
        ['Total Pago', formatar_valor(total_pago)]
    ]
    tabela_geral = Table(dados_geral, colWidths=[2.5*inch, 2.5*inch])
    tabela_geral.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(tabela_geral)
    
    doc.build(story)
    print(f"  ✓ PDF gerado: {nome_arquivo}")

def main():
    """Função principal para executar o script."""
    print("="*60)
    print("GERADOR DE RELATÓRIO DE GASTOS (CONSOLE + PDF) - NUBANK")
    print("="*60)
    
    caminho = input("\nDigite o caminho da pasta com os arquivos CSV\n(ou pressione Enter para usar a pasta atual): ").strip()
    if not caminho:
        caminho = "."
    
    print("\n" + "="*60)
    print(f"\n1. 📂 Processando arquivos em: {Path(caminho).resolve()}")
    df = processar_arquivos_nubank(caminho)
    
    if df is None:
        print("\nProcesso interrompido. Verifique o nome dos arquivos (ex: 'Nubank_*.csv')")
        return
    
    print(f"\n  ✓ Total de {len(df)} transações encontradas em {df['arquivo_origem'].nunique()} arquivo(s).")
    
    print("\n2. 🔄 Limpando e categorizando dados...")
    df = limpar_e_processar_dados(df)
    print(f"  ✓ Dados processados ({len(df)} transações válidas).")
    
    print("\n3. 🖨️  Gerando resumo no console...")
    imprimir_resumo_console(df)
    
    print("\n4. 📄 Gerando relatório PDF...")
    nome_pdf = input("Digite o nome do arquivo PDF (ou Enter para 'resumo_financeiro.pdf'): ").strip()
    if not nome_pdf:
        nome_pdf = "resumo_financeiro.pdf"
    if not nome_pdf.endswith('.pdf'):
        nome_pdf += '.pdf'
    gerar_pdf_resumo(df, nome_pdf)

    print("\n\n" + "="*60)
    print("RESUMO GERAL DO PERÍODO")
    print("="*60)
    print(f"  • Período Analisado...: {df['date'].min().strftime('%d/%m/%Y')} até {df['date'].max().strftime('%d/%m/%Y')}")
    print(f"  • Total de Meses......: {df['mes_ano'].nunique()}")
    print(f"  • Total de Transações.: {len(df)}")
    
    total_gasto = df[df['tipo'] != 'Pagamento']['amount'].sum()
    total_pago = df[df['tipo'] == 'Pagamento']['amount'].sum()
    
    print(f"  • Total Gasto (Compras + IOF): {formatar_valor(total_gasto)}")
    print(f"  • Total Pago..............: {formatar_valor(total_pago)}")
    print("="*60)
    print(f"\n🎉 Processo concluído! PDF salvo como '{nome_pdf}'.\n")


if __name__ == "__main__":
    main()