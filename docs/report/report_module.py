import weasyprint

from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration


def makepdf(html):
    HTML(html).write_pdf("//Users//apung//Destop//newreport.pdf")
