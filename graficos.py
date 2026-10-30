"""Gráfico de médias por disciplina (Matplotlib)."""


def desenhar_medias(figura, medias, nome_aluno):
    """Desenha, em uma Figure do Matplotlib, as barras de média por disciplina.

    `medias` é um dict {disciplina: média}. Serve tanto para a janela do
    Tkinter (matplotlib.figure.Figure) quanto para o terminal (plt.figure()).
    """
    eixo = figura.subplots()
    barras = eixo.bar(list(medias), list(medias.values()), color="#4c72b0")
    eixo.bar_label(barras, fmt="%.2f", padding=2)
    eixo.set_title(f"Média de {nome_aluno}")
    eixo.set_xlabel("Disciplina")
    eixo.set_ylabel("Média")
    eixo.set_ylim(0, 10.8)
    eixo.grid(axis="y", alpha=0.3)
    eixo.tick_params(axis="x", labelrotation=25)
    for rotulo in eixo.get_xticklabels():
        rotulo.set_horizontalalignment("right")
    figura.tight_layout()


def mostrar_medias_aluno(medias, nome_aluno):
    """Abre o gráfico em uma janela do Matplotlib (uso no terminal)."""
    import matplotlib.pyplot as plt

    desenhar_medias(plt.figure(figsize=(8, 4.5)), medias, nome_aluno)
    plt.show()
