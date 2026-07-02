import { PLATFORM_COMMISSION_PERCENT } from "@/lib/utils";

export default function HowItWorksPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
      <h1 className="mb-8 text-2xl font-bold">Как работает СпецАренда</h1>

      <div className="mb-10">
        <h2 className="mb-3 text-lg font-semibold">Для тех, кто арендует</h2>
        <ol className="list-decimal space-y-2 pl-5 text-sm text-gray-600">
          <li>Найдите нужную технику в каталоге по городу, категории и цене.</li>
          <li>Выберите даты аренды и отправьте заявку владельцу.</li>
          <li>Оплатите аренду онлайн через безопасный платёжный шлюз.</li>
          <li>Получите технику в согласованном месте и времени.</li>
        </ol>
      </div>

      <div className="mb-10">
        <h2 className="mb-3 text-lg font-semibold">Для владельцев техники</h2>
        <ol className="list-decimal space-y-2 pl-5 text-sm text-gray-600">
          <li>Зарегистрируйтесь и разместите объявление с фото и ценой.</li>
          <li>Подключите приём выплат в разделе «Выплаты» личного кабинета.</li>
          <li>Получайте заявки на аренду и подтверждайте их.</li>
          <li>
            После оплаты арендатором деньги поступают на ваш счёт за вычетом
            комиссии платформы.
          </li>
        </ol>
      </div>

      <div className="rounded-xl border border-black/5 bg-white p-6">
        <h2 className="mb-2 text-lg font-semibold">Комиссия платформы</h2>
        <p className="text-sm text-gray-600">
          Мы берём комиссию {PLATFORM_COMMISSION_PERCENT}% только с успешных
          сделок — она автоматически добавляется к стоимости аренды для
          арендатора и удерживается платформой при выплате владельцу.
          Размещение объявлений бесплатно.
        </p>
      </div>
    </div>
  );
}
