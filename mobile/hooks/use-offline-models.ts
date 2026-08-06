import { useCallback, useEffect, useRef, useState } from 'react';
import { useFocusEffect } from 'expo-router';
import MLKitTranslate from 'react-native-mlkit-translate';

/**
 * Единая точка работы со скачанными языковыми пакетами ML Kit.
 *
 * Раньше эта логика была скопирована в экраны текста и камеры, и оба
 * повторяли одну ошибку: список моделей читался только при монтировании,
 * а ошибка чтения молча гасилась в console.warn. Из-за этого скачивание
 * «срабатывало через раз» — пакет на самом деле загружался, но экран
 * продолжал показывать кнопку «скачать», пока приложение не перезапустят.
 */

/** Промис `downloadModel` завершается РАНЬШЕ, чем пакет оказывается
 *  на устройстве: сама загрузка продолжается в фоне силами Google Play
 *  Services. Проверено на живом телефоне — «скачал, показал ошибку, а если
 *  не трогать, всё доезжает само».
 *
 *  Поэтому ждём появления пакета в списке, а не доверяем промису. Бюджет
 *  рассчитан на языковой пакет в несколько десятков мегабайт на мобильном
 *  интернете, а не на быстрый Wi-Fi: две минуты. Интервал растёт, чтобы
 *  не дёргать Play Services каждые полсекунды всю дорогу. */
const VERIFY_BUDGET_MS = 180_000;
const VERIFY_FIRST_DELAY_MS = 400;
const VERIFY_MAX_DELAY_MS = 3_000;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function useOfflineModels() {
  const [models, setModels] = useState<string[]>([]);
  const [downloading, setDownloading] = useState<Record<string, boolean>>({});

  /** Языки, для которых загрузка уже идёт: второй тап по той же кнопке
   *  не должен запускать вторую. */
  const inFlight = useRef<Set<string>>(new Set());
  /** Экран ещё жив — иначе прекращаем опрос, чтобы не трогать состояние
   *  размонтированного компонента. */
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  /** Перечитать список. Ошибку не проглатываем — возвращаем наверх,
   *  чтобы вызывающий код мог решить, показывать её или нет. */
  const refresh = useCallback(async (): Promise<string[]> => {
    const list = await MLKitTranslate.getDownloadedModels();
    const normalized = list.map((m) => m.toLowerCase());
    setModels(normalized);
    return normalized;
  }, []);

  /* Обновляем при каждом возвращении на экран, а не только при первом
     открытии: пакет мог быть скачан на соседнем экране или в прошлый заход. */
  useFocusEffect(
    useCallback(() => {
      refresh().catch((err) => console.warn('Не удалось прочитать список моделей:', err));
    }, [refresh]),
  );

  /**
   * Скачать пакет.
   *
   * `ok` — модель действительно появилась на устройстве. `timeout` — не
   * дождались за отведённое время (об этом стоит сказать вслух). `busy` —
   * загрузка этого языка уже идёт, повторный тап просто игнорируем:
   * параллельные загрузки одного пакета — верный способ подвесить экран.
   */
  const download = useCallback(
    async (langCode: string): Promise<'ok' | 'timeout' | 'busy'> => {
      const code = langCode.toLowerCase();
      if (inFlight.current.has(code)) return 'busy';
      inFlight.current.add(code);
      setDownloading((prev) => ({ ...prev, [langCode]: true }));

      try {
        try {
          // requireWifi=false: турист чаще всего в роуминге или на мобильном
          // интернете, и ждать Wi-Fi ему негде.
          await MLKitTranslate.downloadModel(langCode, false);
        } catch (err) {
          // Отказ здесь ещё ничего не значит: на части устройств промис
          // отваливается, пока Play Services продолжает качать в фоне и
          // в итоге доводит дело до конца (поймано на Redmi Note 15 Pro —
          // ошибка появлялась сразу, а пакет доезжал, если не трогать).
          // Поэтому не сдаёмся, а идём проверять список.
          console.warn('downloadModel отказал, проверяем список:', err);
        }

        const deadline = Date.now() + VERIFY_BUDGET_MS;
        let delay = VERIFY_FIRST_DELAY_MS;
        while (Date.now() < deadline) {
          if (!alive.current) return 'busy'; // экран закрыли — молча выходим
          const list = await refresh();
          if (list.includes(code)) return 'ok';
          await wait(delay);
          delay = Math.min(delay * 1.6, VERIFY_MAX_DELAY_MS);
        }
        return 'timeout';
      } finally {
        inFlight.current.delete(code);
        setDownloading((prev) => ({ ...prev, [langCode]: false }));
      }
    },
    [refresh],
  );

  return { models, downloading, refresh, download };
}
