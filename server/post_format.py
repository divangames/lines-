"""Разметка публикаций: единый результат для предпросмотра и Telegram Bot API."""
import re
from urllib.parse import urlsplit

from fastapi import HTTPException

TAGS = {'b':'bold','i':'italic','u':'underline','s':'strikethrough','spoiler':'spoiler',
        'quote':'blockquote','fold':'expandable_blockquote','code':'code','pre':'pre',
        'link':'text_link','time':'date_time'}
TOKEN = re.compile(r'\[(/?)(b|i|u|s|spoiler|quote|fold|code|pre|link|time)(?:=([^\]\n]*))?\]')
INLINE = {'bold','italic','underline','strikethrough','spoiler'}


def parse(source, limit):
    stack, entities, pieces = [], [], []
    length = pos = 0
    def append(value):
        nonlocal length
        pieces.append(value)
        length += len(value.encode('utf-16-le'))//2
    for match in TOKEN.finditer(source):
        closing, tag, arg = match.groups()
        if stack and stack[-1][0] in ('pre','code') and not (closing and tag==stack[-1][0]):
            continue
        append(source[pos:match.start()])
        pos = match.end()
        if closing:
            if not stack or stack[-1][0]!=tag or arg is not None:
                raise HTTPException(422,'Проверьте порядок открывающих и закрывающих меток оформления')
            _, entity = stack.pop()
            entity['length']=length-entity['offset']
            if entity['length']: entities.append(entity)
            continue
        kind=TAGS[tag]
        if any(kind==e['type'] or tag in ('code','pre') or (kind not in INLINE and e['type'] not in INLINE)
               for _,e in stack):
            raise HTTPException(422,'Эти виды оформления нельзя вкладывать друг в друга')
        entity={'type':kind,'offset':length}
        if tag=='link':
            if not arg or not re.match(r'^https?://',arg,re.I) or re.search(r'[\s<>]',arg):
                raise HTTPException(422,'Укажите полный адрес ссылки с https:// или http://')
            try: valid=bool(urlsplit(arg).hostname)
            except ValueError: valid=False
            if not valid: raise HTTPException(422,'Проверьте адрес ссылки')
            entity['url']=arg
        elif tag=='time':
            if not arg or len(arg)>10 or not arg.isascii() or not arg.isdigit() or not 0<int(arg)<=4102444800:
                raise HTTPException(422,'Выберите дату и время для вставки')
            entity['unix_time']=int(arg)
        elif tag=='pre' and arg:
            if not re.fullmatch(r'[\w.+#-]{1,32}',arg): raise HTTPException(422,'Проверьте название языка кода')
            entity['language']=arg
        elif arg is not None: raise HTTPException(422,'Лишний параметр оформления')
        stack.append((tag,entity))
    append(source[pos:])
    if stack: raise HTTPException(422,'Закройте метку оформления в тексте')
    body=''.join(pieces)
    if len(body)>limit: raise HTTPException(422,f'После оформления допустимо до {limit} символов')
    if len(entities)>100: raise HTTPException(422,'Допустимо до 100 фрагментов оформления')
    return body,sorted(entities,key=lambda e:(e['offset'],-e['length']))
