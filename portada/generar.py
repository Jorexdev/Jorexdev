"""Genera la portada del perfil (README.md + img/*.svg): la mesa de backstage.

    python portada/generar.py

Solo usa la librería estándar. Lo lanza también la Action `portada.yml` para
mantener al día el último reel (feed de YouTube) y el número de The Weekly Fork.

- Las fuentes (DM Sans, DM Mono, Permanent Marker) se incrustan como subconjunto
  con solo los caracteres usados: GitHub sirve los SVG como <img> y desde ahí
  no se pueden cargar fuentes de fuera. Se guardan en portada/fuentes/.
- Cada SVG se escribe como img/<nombre>-<hash>.svg: si cambia el contenido cambia
  el nombre y GitHub no sirve la versión vieja. Los SVG que dejan de usarse se borran.
"""
import base64, datetime, hashlib, html, json, pathlib, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

AQUI = pathlib.Path(__file__).resolve().parent
REPO = AQUI.parent
IMG = REPO / "img"
FUENTES = AQUI / "fuentes"
ESTADO = AQUI / "estado.json"

CANAL_YT = "UC1pId9VnyAfsKKmFjnGDGaw"
# The Weekly Fork sale los viernes a las 15:00 (Madrid). Si algún viernes no sale,
# se mueve esta referencia: número que sale en esa fecha.
NEWSLETTER_REF = (12, datetime.date(2026, 10, 16))

FOREST, OLIVA, OLIVA_LT, LIMA, CREAM, SAGE, BG = "#1C2B1A", "#606C38", "#A3B067", "#d4e87a", "#E8EDD4", "#C5CEAB", "#0a1208"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

FONTS = {  # clase -> (familia de Google Fonts, eje, respaldo)
    "s4": ("DM Sans", "wght@400", "sans-serif"),
    "s5": ("DM Sans", "wght@500", "sans-serif"),
    "s7": ("DM Sans", "wght@700", "sans-serif"),
    "m4": ("DM Mono", "wght@400", "monospace"),
    "m5": ("DM Mono", "wght@500", "monospace"),
    "h":  ("Permanent Marker", "", "cursive"),
}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()


def e(s):
    return html.escape(s, quote=False)


def T(x, y, s, cls, size, fill, anchor="start", extra=""):
    return f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" {extra}>{e(s)}</text>'


def fade(values, times, dur=6, begin=0):
    return f'<animate attributeName="opacity" values="{values}" keyTimes="{times}" dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>'


EASE = 'calcMode="spline" keyTimes="0;.5;1" keySplines=".45 0 .55 1;.45 0 .55 1"'
SHADOW = '<filter id="sh" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="10" flood-color="#000" flood-opacity=".45"/></filter>'
SHADOW_SOFT = '<filter id="shs" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#000" flood-opacity=".35"/></filter>'
NOISE = '<filter id="noise"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .07 0"/></filter>'
GLOW = '<filter id="glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur in="SourceGraphic" result="b"><animate attributeName="stdDeviation" values="2;8;2" dur="2.4s" repeatCount="indefinite"/></feGaussianBlur><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'

SVGS = {}


def svg(name, w, h, body, defs=""):
    SVGS[name] = (w, h, defs, body)


def hang_tag(label, ay, top, begin):
    """Etiqueta colgante con la acción del enlace; se balancea desde su punto de anclaje."""
    cx = 136
    tw = len(label) * 8.1
    w = tw + 50
    return f"""
<g><animateTransform attributeName="transform" type="rotate" values="-3 {cx} {ay};3 {cx} {ay};-3 {cx} {ay}" dur="4s" begin="{begin}s" repeatCount="indefinite" {EASE}/>
  <path d="M{cx} {ay} C {cx-6} {ay+10}, {cx+6} {top-6}, {cx} {top+7}" stroke="#9aa08c" stroke-width="1.6" fill="none"/>
  <rect x="{cx - w/2}" y="{top}" width="{w}" height="40" rx="7" fill="{LIMA}" filter="url(#sh)"/>
  <circle cx="{cx}" cy="{top+8}" r="3.2" fill="{FOREST}"/>
  {T(cx - 9, top + 31, label, "m5", 11, FOREST, "middle", 'letter-spacing="1.4"')}
  <g><animateTransform attributeName="transform" type="translate" values="0 0;3 0;0 0" dur="1.4s" repeatCount="indefinite"/>
  <path d="M{cx + tw/2 + 1} {top+27} h12 m-5 -5 l5 5 l-5 5" stroke="{FOREST}" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></g>
</g>"""


def wrap(text, max_chars, max_lines):
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + (1 if cur else 0) <= max_chars:
            cur = f"{cur} {word}".strip()
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max_chars - 1].rstrip() + "…"
    return lines


# ---------------------------------------------------------------- datos que cambian

def numero_newsletter(ahora):
    """Número de la próxima edición (la del viernes que viene, o la de hoy si aún no son las 15:00)."""
    try:
        from zoneinfo import ZoneInfo
        local = ahora.astimezone(ZoneInfo("Europe/Madrid"))
    except Exception:
        local = ahora + datetime.timedelta(hours=2)
    dias = (4 - local.weekday()) % 7
    viernes = local.date() + datetime.timedelta(days=dias)
    if dias == 0 and local.hour >= 15:
        viernes += datetime.timedelta(days=7)
    num, fecha = NEWSLETTER_REF
    return num + (viernes - fecha).days // 7


def ultimo_reel(estado):
    """Último vídeo del canal de YouTube; si falla la red, el último conocido."""
    try:
        feed = ET.fromstring(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={CANAL_YT}"))
        ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        entry = feed.find("a:entry", ns)
        vid = entry.find("yt:videoId", ns).text
        titulo = re.sub(r"\s*#\w+", "", entry.find("a:title", ns).text).strip()
        titulo = re.sub(r"\s*\([^)]*\)$", "", titulo) or titulo  # sin el paréntesis final
        url = entry.find("a:link", ns).get("href")
        miniatura = base64.b64encode(get(f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")).decode()
        estado["reel"] = {"id": vid, "titulo": titulo, "url": url, "miniatura": miniatura}
    except Exception as err:
        print("feed de YouTube no disponible, uso el último conocido:", err)
    return estado["reel"]


# ---------------------------------------------------------------- piezas

def badge(avatar):
    """Lanyard + acreditación ALL ACCESS, colgando de (230, 0) en coordenadas de la cabecera."""
    return f'''
<g>
  <animateTransform attributeName="transform" type="rotate" values="-2.5 230 0;2.5 230 0;-2.5 230 0" dur="6s" repeatCount="indefinite" {EASE}/>
  <path d="M285 -12 L240 122" stroke="#4d5a2c" stroke-width="20"/>
  <path id="strapL" d="M175 -12 L220 122" stroke="{OLIVA}" stroke-width="20"/>
  <text class="m5" font-size="9" fill="{LIMA}" letter-spacing="2" dy="3"><textPath href="#strapL">JOREX.DEV · JOREX.DEV · JOREX.DEV</textPath></text>
  <rect x="217" y="114" width="26" height="24" rx="5" fill="#b9bfae"/><rect x="221" y="117" width="18" height="4" rx="2" fill="#e8ebe1"/>
  <g filter="url(#sh)"><rect x="115" y="135" width="230" height="315" rx="16" fill="{CREAM}"/></g>
  <clipPath id="card"><rect x="115" y="135" width="230" height="315" rx="16"/></clipPath>
  <g clip-path="url(#card)">
    <rect x="115" y="168" width="230" height="34" fill="{FOREST}"/>
    {T(230, 190, "BACKSTAGE", "m5", 11, LIMA, "middle", 'letter-spacing="5"')}
    <rect x="115" y="426" width="230" height="24" fill="{LIMA}"/>
    {T(230, 442, "ALL ACCESS", "m5", 11, FOREST, "middle", 'letter-spacing="6"')}
    <g><animateTransform attributeName="transform" type="translate" values="-160 0;-160 0;420 0" keyTimes="0;.6;1" dur="5s" repeatCount="indefinite"/>
      <rect x="115" y="120" width="70" height="360" fill="url(#sheen)" transform="skewX(-18)"/></g>
  </g>
  <rect x="205" y="146" width="50" height="9" rx="4.5" fill="{BG}" opacity=".85"/>
  <clipPath id="ph"><rect x="170" y="216" width="120" height="120" rx="14"/></clipPath>
  <image href="{avatar}" x="170" y="216" width="120" height="120" clip-path="url(#ph)" preserveAspectRatio="xMidYMid slice"/>
  <rect x="170" y="216" width="120" height="120" rx="14" fill="none" stroke="{FOREST}" stroke-width="3"/>
  {T(230, 377, "JOREX", "s7", 38, FOREST, "middle", 'letter-spacing="2"')}
  {T(230, 397, "Jorge Barba Polán", "s4", 13, OLIVA, "middle")}
  {T(230, 416, "SOFTWARE ANALYST · SPEAKER", "m4", 9.5, FOREST, "middle", 'letter-spacing="1.2"')}
</g>'''


def stage(w, h):
    return f'''
<rect width="{w}" height="{h}" rx="22" fill="{BG}"/>
<rect width="{w}" height="{h}" rx="22" fill="url(#spot)"><animate attributeName="opacity" values=".7;1;.7" dur="7s" repeatCount="indefinite"/></rect>
<clipPath id="stageclip"><rect width="{w}" height="{h}" rx="22"/></clipPath>
<rect width="{w}" height="{h}" filter="url(#noise)" clip-path="url(#stageclip)"/>'''


STAGE_DEFS = f'''{SHADOW}{SHADOW_SOFT}{NOISE}{GLOW}
<radialGradient id="spot" cx="50%" cy="0%" r="85%"><stop offset="0" stop-color="#2c4124"/><stop offset="1" stop-color="{BG}" stop-opacity="0"/></radialGradient>
<linearGradient id="sheen" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'''


def postit(lines, width, size):
    """Pósit lima con cinta y un subrayado que se dibuja solo; origen en su esquina superior izquierda."""
    return f'''
  <animateTransform attributeName="transform" type="translate" additive="sum" values="0 0;0 -4;0 0" dur="4s" repeatCount="indefinite" {EASE}/>
  <rect x="0" y="0" width="{width}" height="86" fill="{LIMA}" filter="url(#shs)"/>
  <rect x="{width/2 - 33}" y="-10" width="66" height="20" fill="{CREAM}" opacity=".55" transform="rotate(-5 {width/2} 0)"/>
  {T(16, 36, lines[0], "h", size, FOREST)}
  {T(16, 68, lines[1], "h", size, FOREST)}
  <path d="M14 76 C 40 70, 70 80, 96 72" stroke="{OLIVA}" stroke-width="3" fill="none" stroke-linecap="round" stroke-dasharray="130" stroke-dashoffset="130">
    <animate attributeName="stroke-dashoffset" values="130;0;0;130" keyTimes="0;.25;.85;1" dur="4s" repeatCount="indefinite"/></path>'''


def hero(avatar):
    svg("mesa-hero", 840, 480, f'''{stage(840, 480)}{badge(avatar)}
{T(420, 112, "// SOFTWARE ANALYST · DIVULGADOR · SPEAKER", "m4", 12, OLIVA_LT, "start", 'letter-spacing="1.5"')}
{T(418, 178, "Hola, soy", "s7", 58, CREAM)}
<text x="416" y="252" class="s7" font-size="78" fill="{LIMA}" filter="url(#glow)">Jorex.</text>
{T(420, 296, "Explico backend en Instagram, TikTok y", "s4", 17, SAGE)}
{T(420, 320, "YouTube, y llevo Bytes Colaborativos:", "s4", 17, SAGE)}
{T(420, 344, "una comunidad de proyectos reales.", "s4", 17, SAGE)}
<g transform="translate(540 368) rotate(3)">{postit(["Aprende backend", "GRATIS en jorex.dev"], 262, 20)}</g>''', STAGE_DEFS)


def hero_movil(avatar):
    """La misma cabecera en vertical, para pantallas estrechas (<picture> con media query)."""
    svg("mesa-hero-movil", 420, 740, f'''{stage(420, 740)}
<g transform="translate(26 0) scale(.8)">{badge(avatar)}</g>
{T(210, 412, "// SOFTWARE ANALYST · SPEAKER", "m4", 11, OLIVA_LT, "middle", 'letter-spacing="1.5"')}
{T(210, 466, "Hola, soy", "s7", 46, CREAM, "middle")}
<text x="210" y="530" class="s7" font-size="64" fill="{LIMA}" filter="url(#glow)" text-anchor="middle">Jorex.</text>
{T(210, 570, "Explico backend en Instagram,", "s4", 17, SAGE, "middle")}
{T(210, 594, "TikTok y YouTube, y llevo", "s4", 17, SAGE, "middle")}
{T(210, 618, "Bytes Colaborativos.", "s4", 17, SAGE, "middle")}
<g transform="translate(78 632) rotate(2)">{postit(["Aprende backend", "GRATIS en jorex.dev"], 262, 20)}</g>''', STAGE_DEFS)


def javaprep():
    fichas = [("Streams", "¿lazy o eager?"), ("Optional", "¿orElse u orElseGet?"), ("SOLID", "¿qué significa la L?"), ("Genéricos", "¿qué es PECS?")]
    ficha_svg = "".join(
        f'<g opacity="0">{fade("0;1;1;0;0", "0;.04;.22;.25;1", 8, i*2)}'
        f'{T(136, 150, c, "s7", 27, FOREST, "middle")}{T(136, 176, q, "m4", 11, OLIVA, "middle")}</g>' for i, (c, q) in enumerate(fichas))
    svg("mesa-javaprep", 272, 352, f'''
<g transform="rotate(-3 136 150)">
  <rect x="34" y="72" width="212" height="152" rx="3" fill="#cfd6b8" transform="rotate(7 140 142)" filter="url(#sh)"/>
  <rect x="30" y="68" width="212" height="152" rx="3" fill="#e2e7cf" transform="rotate(-5 136 138)"/>
  <rect x="30" y="66" width="212" height="152" rx="3" fill="#fbfaf4"/>
  <line x1="30" y1="96" x2="242" y2="96" stroke="{OLIVA_LT}" stroke-width="1.2"/>
  <line x1="30" y1="194" x2="242" y2="194" stroke="#e4e7d8"/>
  {T(44, 86, "JAVA-PREP · ENTREVISTA", "m5", 9, OLIVA, "start", 'letter-spacing="2"')}
  {ficha_svg}
  <path d="M206 52 v34 a8 8 0 0 0 16 0 v-40 a5 5 0 0 0 -10 0 v36" fill="none" stroke="#9aa08c" stroke-width="2.4" stroke-linecap="round"/>
  {T(136, 210, "40 módulos para tu entrevista backend", "s4", 10.5, OLIVA, "middle")}
  <rect x="66" y="228" width="140" height="38" fill="{LIMA}" transform="rotate(-3 136 247)" filter="url(#sh)"/>
  {T(136, 256, "java-prep", "h", 24, FOREST, "middle", 'transform="rotate(-3 136 247)"')}
</g>{hang_tag("VER EN GITHUB", 262, 288, 0)}''', SHADOW)


def bytes_flyer():
    tabs = []
    for i in range(7):
        x = 38 + i * 28
        if i == 4:
            continue  # una tira ya arrancada
        flutter = f'<animateTransform attributeName="transform" type="rotate" values="0 {x+14} 206;-6 {x+14} 206;0 {x+14} 206" dur="3s" repeatCount="indefinite"/>' if i == 5 else ""
        tabs.append(f'<g>{flutter}<rect x="{x}" y="206" width="28" height="66" fill="{CREAM}"/><line x1="{x}" y1="206" x2="{x}" y2="272" stroke="{OLIVA}" stroke-dasharray="3 3" stroke-width=".8"/>'
                    f'<text class="m4" font-size="9" fill="{FOREST}" transform="translate({x+18} 266) rotate(-90)" letter-spacing="1">DISCORD</text></g>')
    svg("mesa-bytes", 272, 352, f'''
<g transform="rotate(2 136 150)">
  <g filter="url(#sh)"><rect x="34" y="22" width="204" height="184" fill="{CREAM}"/>{"".join(tabs)}</g>
  <line x1="34" y1="206" x2="238" y2="206" stroke="{OLIVA}" stroke-dasharray="3 3" stroke-width=".8"/>
  {T(136, 58, "SE BUSCA", "m5", 11, OLIVA, "middle", 'letter-spacing="5"')}
  {T(136, 94, "Bytes", "s7", 28, FOREST, "middle")}
  {T(136, 122, "Colaborativos", "s7", 24, FOREST, "middle")}
  {T(136, 150, "Proyectos reales en equipo.", "s4", 12, FOREST, "middle")}
  {T(136, 167, "Empresas buscando talento.", "s4", 12, FOREST, "middle")}
  {T(136, 194, "¡arranca uno!", "h", 17, OLIVA, "middle", 'transform="rotate(-4 136 190)"')}
  <circle cx="136" cy="30" r="8" fill="{LIMA}" stroke="{FOREST}" stroke-width="2"/><circle cx="133" cy="27" r="2.5" fill="#fff" opacity=".8"/>
</g>{hang_tag("ENTRAR AL DISCORD", 268, 288, .7)}''', SHADOW)


def fork(numero):
    svg("mesa-fork", 272, 352, f'''
<g transform="rotate(-2 136 160)">
  <rect x="21" y="92" width="230" height="156" rx="6" fill="#a9b48d" filter="url(#sh)"/>
  <g><animateTransform attributeName="transform" type="translate" values="0 0;0 -34;0 -34;0 0" keyTimes="0;.3;.7;1" dur="5s" repeatCount="indefinite"/>
    <rect x="38" y="96" width="196" height="120" rx="3" fill="#fbfaf4"/>
    {T(54, 120, f"Nº {numero} · VIERNES", "m5", 9, OLIVA, "start", 'letter-spacing="2"')}
    <rect x="54" y="130" width="150" height="5" rx="2.5" fill="#dfe3cf"/><rect x="54" y="142" width="120" height="5" rx="2.5" fill="#dfe3cf"/>
  </g>
  <path d="M21 128 L136 186 L251 128 L251 242 Q251 248 245 248 L27 248 Q21 248 21 242 Z" fill="{SAGE}"/>
  <path d="M21 128 L136 186 L251 128" stroke="#a9b48d" fill="none"/>
  <g transform="translate(196 150)">
    <rect width="44" height="52" fill="#fbfaf4" stroke="#fbfaf4" stroke-width="4" stroke-dasharray="2 2"/>
    <rect x="5" y="5" width="34" height="42" fill="{FOREST}"/>
    {T(22, 32, "TWF", "s7", 12, LIMA, "middle")}
    <circle cx="-6" cy="34" r="22" fill="none" stroke="{OLIVA}" stroke-width="1.5" stroke-dasharray="3 2" opacity=".8"/>
    {T(-6, 31, "VIERNES", "m5", 6.5, OLIVA, "middle")}
    {T(-6, 41, "15:00", "m5", 7, OLIVA, "middle")}
  </g>
  {T(38, 220, "The Weekly Fork", "h", 20, FOREST)}
  {T(38, 238, "newsletter semanal de desarrollo", "s4", 10.5, FOREST)}
</g>{hang_tag("SUSCRIBIRME", 246, 288, 1.4)}''', SHADOW)


def charlas():
    """Escaleta en una tablilla: las charlas, con un rotulador que las va marcando."""
    filas = [(122, "01", ["Self-Contained Systems"], "MADRIDJUG · MEETUP"),
             (180, "02", ["Mini-juegos de", "programación e IA"], "CODEMOTION MADRID 2026")]
    cuerpo = []
    for i, (y, n, titulo, sitio) in enumerate(filas):
        cuerpo.append(
            f'<rect x="58" y="{y-17}" width="0" height="22" fill="{LIMA}" opacity=".75">'
            f'<animate attributeName="width" values="0;0;168;168;0" keyTimes="0;{.1+i*.35:.2f};{.25+i*.35:.2f};.92;1" dur="7s" repeatCount="indefinite"/></rect>'
            + T(46, y, n, "m5", 11, OLIVA)
            + "".join(T(70, y + k * 17, linea, "s7", 13, FOREST) for k, linea in enumerate(titulo))
            + T(70, y + len(titulo) * 17 + 2, sitio, "m4", 8.5, OLIVA, "start", 'letter-spacing="1.2"'))
    svg("mesa-charlas", 272, 380, f'''
<g transform="rotate(-2 136 160)">
  <rect x="26" y="26" width="220" height="270" rx="12" fill="#3a3326" filter="url(#sh)"/>
  <rect x="36" y="44" width="200" height="242" rx="2" fill="#fbfaf4"/>
  <rect x="96" y="18" width="80" height="34" rx="6" fill="#b9bfae"/><rect x="112" y="24" width="48" height="8" rx="4" fill="#8c917f"/>
  {T(48, 78, "ESCALETA · CHARLAS", "m5", 9.5, OLIVA, "start", 'letter-spacing="2.4"')}
  <line x1="48" y1="88" x2="224" y2="88" stroke="{OLIVA_LT}"/>
  {"".join(cuerpo)}
  {T(136, 262, "¿la próxima, en tu evento?", "h", 15, OLIVA, "middle", 'transform="rotate(-3 136 258)"')}
</g>{hang_tag("INVÍTAME A TU EVENTO", 292, 316, .3)}''', SHADOW)


def reel(datos):
    lineas = wrap(datos["titulo"], 24, 2)
    textos = "".join(T(136, 268 + i * 16, l, "s7", 12.5, FOREST, "middle") for i, l in enumerate(lineas))
    svg("mesa-reel", 272, 380, f'''
<g transform="rotate(3 136 160)">
  <rect x="36" y="14" width="200" height="290" rx="3" fill="#f5f4ec" filter="url(#sh)"/>
  <svg x="48" y="26" width="176" height="214" viewBox="140 58 200 243" preserveAspectRatio="xMidYMid slice">
    <image width="480" height="360" href="data:image/jpeg;base64,{datos["miniatura"]}"/></svg>
  <rect x="48" y="26" width="176" height="214" fill="url(#oscuro)"/>
  <circle cx="136" cy="133" r="24" fill="{CREAM}" opacity=".92"><animate attributeName="r" values="24;27;24" dur="1.8s" repeatCount="indefinite"/></circle>
  <path d="M129 121 L129 145 L149 133 Z" fill="{FOREST}"/>
  <rect x="60" y="228" width="152" height="3" rx="1.5" fill="#fff" opacity=".35"/>
  <rect x="60" y="228" width="0" height="3" rx="1.5" fill="{LIMA}"><animate attributeName="width" values="0;152" dur="8s" repeatCount="indefinite"/></rect>
  <rect x="150" y="34" width="66" height="20" rx="10" fill="#ff4d4d"/>
  <circle cx="161" cy="44" r="3.5" fill="#fff"><animate attributeName="opacity" values="1;.3;1" dur="1.2s" repeatCount="indefinite"/></circle>
  {T(190, 48, "NUEVO", "m5", 9, "#fff", "middle", 'letter-spacing="1.5"')}
  {T(136, 254, "ÚLTIMO REEL", "m5", 9, OLIVA, "middle", 'letter-spacing="2.4"')}
  {textos}
  <rect x="104" y="2" width="64" height="22" fill="{CREAM}" opacity=".6" transform="rotate(-4 136 13)"/>
</g>{hang_tag("VER EL REEL", 310, 322, 1)}''', SHADOW + f'<linearGradient id="oscuro" x1="0" y1="0" x2="0" y2="1"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></linearGradient>')


def sticker(name, label, fill, fg, rot, w, extra_defs="", under=""):
    h = 58
    svg(name, w, h + 18, f'''
<g transform="rotate({rot} {w/2} {(h+18)/2})" filter="url(#shs)">
  <rect x="8" y="9" width="{w-16}" height="{h}" rx="{h/2}" fill="#ffffff"/>
  <rect x="13" y="14" width="{w-26}" height="{h-10}" rx="{(h-10)/2}" fill="{fill}"/>
  {under}
  {T(w/2, 9 + h/2 + 5.5, label, "s7", 15, fg, "middle")}
</g>''', SHADOW_SOFT + extra_defs)


def stickers():
    ig = '<linearGradient id="ig" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#fcaf45"/><stop offset=".45" stop-color="#e1306c"/><stop offset="1" stop-color="#5b51d8"/></linearGradient>'
    sticker("st-web", "jorex.dev", FOREST, LIMA, -4, 124)
    sticker("st-ig", "instagram", "url(#ig)", "#fff", 3, 128, ig)
    sticker("st-tt", "tiktok", "#111", "#fff", -3, 100, "",
            T(48.5, 42.5, "tiktok", "s7", 15, "#25F4EE", "middle") + T(51.5, 44.5, "tiktok", "s7", 15, "#FE2C55", "middle"))
    sticker("st-yt", "youtube", "#FF0033", "#fff", 4, 112)
    sticker("st-in", "linkedin", "#0A66C2", "#fff", -2, 114)
    sticker("st-dc", "discord", "#5865F2", "#fff", 3, 108)
    sticker("st-nl", "newsletter", LIMA, FOREST, -3, 128)


# ---------------------------------------------------------------- fuentes y escritura

TEXT_RE = re.compile(r'<text\b[^>]*class="(\w+)"[^>]*>(.*?)</text>', re.S)


def fuentes():
    usados = {k: set() for k in FONTS}
    for _, _, _, body in SVGS.values():
        for cls, inner in TEXT_RE.findall(body):
            usados[cls].update(html.unescape(re.sub(r"<[^>]+>", "", inner)))
    datos = {}
    FUENTES.mkdir(exist_ok=True)
    for cls, (fam, eje, _) in FONTS.items():
        chars = "".join(sorted(usados[cls]))
        if not chars.strip():
            continue
        f = FUENTES / f"{cls}-{hashlib.sha1(chars.encode()).hexdigest()[:10]}.woff2"
        if not f.exists():
            q = urllib.parse.quote(fam) + (":" + eje if eje else "")
            css = get(f"https://fonts.googleapis.com/css2?family={q}&text={urllib.parse.quote(chars)}").decode()
            f.write_bytes(get(re.search(r"url\((https://[^)]+)\)", css).group(1)))
        datos[cls] = base64.b64encode(f.read_bytes()).decode()
    vivos = {f"{c}-{hashlib.sha1(''.join(sorted(usados[c])).encode()).hexdigest()[:10]}.woff2" for c in datos}
    for f in FUENTES.glob("*.woff2"):
        if f.name not in vivos:
            f.unlink()
    return datos


def escribir():
    datos = fuentes()
    IMG.mkdir(exist_ok=True)
    rutas = {}
    for name, (w, h, defs, body) in SVGS.items():
        classes = sorted({c for c, _ in TEXT_RE.findall(body)})
        css = "".join(
            f"@font-face{{font-family:'j{c}';src:url(data:font/woff2;base64,{datos[c]}) format('woff2');}}"
            f".{c}{{font-family:'j{c}','{FONTS[c][0]}',{FONTS[c][2]};}}" for c in classes)
        doc = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
               f'<defs><style>{css}</style>{defs}</defs>{body}</svg>')
        nombre = f"{name}-{hashlib.sha1(doc.encode()).hexdigest()[:8]}.svg"
        (IMG / nombre).write_text(doc, encoding="utf-8", newline="\n")
        rutas[name] = f"img/{nombre}"
    for f in IMG.glob("*"):
        if f"img/{f.name}" not in rutas.values():
            f.unlink()
    return rutas


def readme(r, reel_url):
    a = lambda href, key, alt: f'<a href="{href}"><img src="{r[key]}" alt="{e(alt)}"/></a>'
    redes = [("https://jorex.dev/", "st-web", "jorex.dev"), ("https://instagram.com/jorex.dev", "st-ig", "Instagram"),
             ("https://tiktok.com/@jorex.dev", "st-tt", "TikTok"), ("https://youtube.com/@jorexdev", "st-yt", "YouTube"),
             ("https://linkedin.com/in/jorge-barba-polan", "st-in", "LinkedIn"), ("https://discord.gg/zsZqS7wxXU", "st-dc", "Discord"),
             ("https://jorex.dev/#newsletter", "st-nl", "Newsletter")]
    return f'''<!-- Generado con portada/generar.py: no editar a mano. -->
<p align="center">
  <a href="https://jorex.dev/"><picture><source media="(max-width: 600px)" srcset="{r["mesa-hero-movil"]}"><img src="{r["mesa-hero"]}" width="100%" alt="Hola, soy Jorex. Software analyst, divulgador y speaker. Explico backend en Instagram, TikTok y YouTube y llevo Bytes Colaborativos. Aprende backend gratis en jorex.dev"/></picture></a>
</p>

<p align="center">
  {a("https://github.com/Jorexdev/java-prep", "mesa-javaprep", "java-prep: 40 módulos para preparar tu entrevista técnica de backend en Java")}{a("https://discord.gg/zsZqS7wxXU", "mesa-bytes", "Bytes Colaborativos: proyectos reales en equipo, empresas buscando talento")}{a("https://jorex.dev/#newsletter", "mesa-fork", "The Weekly Fork: newsletter semanal de desarrollo")}
</p>

<p align="center">
  {a("mailto:jorgebp@jorex.dev", "mesa-charlas", "Charlas: Self-Contained Systems en MadridJUG y mini-juegos de programación e IA en Codemotion Madrid 2026. Invítame a tu evento")}{a(reel_url, "mesa-reel", "Último reel")}
</p>

<p align="center">
  {"".join(a(h, k, alt) for h, k, alt in redes)}
</p>
'''


def main():
    estado = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}
    avatar = "data:image/jpeg;base64," + base64.b64encode((AQUI / "avatar.jpg").read_bytes()).decode()
    datos_reel = ultimo_reel(estado)
    hero(avatar)
    hero_movil(avatar)
    javaprep()
    bytes_flyer()
    fork(numero_newsletter(datetime.datetime.now(datetime.timezone.utc)))
    charlas()
    reel(datos_reel)
    stickers()
    rutas = escribir()
    (REPO / "README.md").write_text(readme(rutas, datos_reel["url"]), encoding="utf-8", newline="\n")
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(rutas)} SVG; reel: {datos_reel['titulo']}")


if __name__ == "__main__":
    main()
