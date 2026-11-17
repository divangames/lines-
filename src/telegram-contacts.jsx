import React from 'react';
import {ArrowUpRight, MessagesSquare, Send} from 'lucide-react';

export function TelegramContacts({settings}) {
  return <section className="telegram-contacts" aria-labelledby="telegram-contacts-title">
    <div className="telegram-contacts-intro">
      <h2 id="telegram-contacts-title">Остаёмся на связи.</h2>
      <p>Новости проекта и помощь с подключением — в Telegram.</p>
    </div>
    <div className="telegram-contact-links">
      {settings.telegram_news_url&&<a className="telegram-contact" href={settings.telegram_news_url} target="_blank" rel="noopener noreferrer">
        <Send size={24} aria-hidden="true"/>
        <span><strong>Новости в Telegram</strong><span>Подписывайтесь на нашу группу, чтобы следить за обновлениями и объявлениями.</span><b>Открыть группу <ArrowUpRight size={17} aria-hidden="true"/></b></span>
      </a>}
      <a className="telegram-contact" href="https://t.me/linesonline_bot?start=support" target="_blank" rel="noopener noreferrer">
        <MessagesSquare size={24} aria-hidden="true"/>
        <span><strong>Нужна помощь?</strong><span>Напишите нашему боту поддержки в Telegram, если возникли вопросы о доступе или подключении.</span><b>Написать в поддержку <ArrowUpRight size={17} aria-hidden="true"/></b></span>
      </a>
    </div>
  </section>;
}
