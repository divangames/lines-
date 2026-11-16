from pathlib import Path
p=Path(__file__).resolve().parents[1]/'src/main.jsx'
s=p.read_text(encoding='utf-8')
s=s.replace("<button className={client==='happ'?'chosen':''}","<button aria-pressed={client==='happ'} className={client==='happ'?'chosen':''}")
s=s.replace("<button className={client==='v2ray'?'chosen':''}","<button aria-pressed={client==='v2ray'} className={client==='v2ray'?'chosen':''}")
public=s.index('function PublicShell(')
admin=s.index('function AdminShell(')
tail=s.index('function LoginPage(')
parts=[s[:public],s[public:admin],s[admin:tail],s[tail:]]
for index,identifier in ((1,'public-navigation'),(2,'admin-navigation')):
    parts[index]=parts[index].replace("label={menu?'Закрыть меню':'Открыть меню'}", "aria-expanded={menu} aria-controls='"+identifier+"' label={menu?'Закрыть меню':'Открыть меню'}",1)
    parts[index]=parts[index].replace('<aside className=',"<aside id='"+identifier+"' className=",1)
p.write_text(''.join(parts),encoding='utf-8')
