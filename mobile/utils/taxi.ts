/** Вызов такси — одна точка входа для карты и для ИИ-гида.
 *
 * Раньше этот код жил только на экране карты, и команда гида «вызови такси»
 * шла кружным путём: приложение переключалось на вкладку «Карта», карта
 * забирала команду и уже оттуда открывала Яндекс Go. Карта при этом не нужна
 * вовсе, а лишний переход добавлял задержку и возвращал пользователя не туда.
 */

import { Linking } from 'react-native';
import * as Location from 'expo-location';

import type { MyCoords } from './location';

/** Сколько ждём координаты, прежде чем открыть такси без них.
 *  Стартовую точку Яндекс Go определит сам — ждать ради неё холодный GPS
 *  (а это бывают десятки секунд в помещении) незачем. */
const COORDS_TIMEOUT_MS = 1500;

export interface TaxiDestination {
  name?: string | null;
  lat: number;
  lng: number;
}

/** Координаты «сейчас», но не дольше полутора секунд: сначала последняя
 *  известная позиция (она отдаётся мгновенно), потом свежая — что успеет. */
async function coordsQuickly(): Promise<MyCoords | null> {
  try {
    const { status } = await Location.getForegroundPermissionsAsync();
    if (status !== 'granted') return null;

    const last = await Location.getLastKnownPositionAsync();
    if (last) return { lat: last.coords.latitude, lng: last.coords.longitude };

    const fresh = await Promise.race([
      Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), COORDS_TIMEOUT_MS)),
    ]);
    return fresh ? { lat: fresh.coords.latitude, lng: fresh.coords.longitude } : null;
  } catch {
    return null;
  }
}

function params(dest: TaxiDestination, me: MyCoords | null): string {
  const p = new URLSearchParams({
    'end-lat': String(dest.lat),
    'end-lon': String(dest.lng),
    ref: 'aiuzguide',
    appmetrica_tracking_id: '1178268795219780156',
  });
  if (me) {
    p.set('start-lat', String(me.lat));
    p.set('start-lon', String(me.lng));
  }
  return p.toString();
}

/**
 * Открыть заказ такси до точки. Возвращает true, если система приняла ссылку.
 *
 * Сначала пробуем схему самого приложения — тогда Яндекс Go открывается
 * сразу. Веб-ссылка оставлена запасной: она ведёт через редирект AppMetrica,
 * то есть сначала откроется браузер и только потом такси, а если приложения
 * нет — Яндекс уведёт в магазин.
 *
 * Проверять `canOpenURL` не пробуем: на Android 11+ он требует объявления
 * схемы в манифесте, а манифест у нас пересоздаётся при сборке. Попытка
 * с перехватом ошибки даёт тот же результат без этой зависимости.
 *
 * Важно понимать предел: успех означает лишь, что система приняла ссылку.
 * Открылось ли приложение на самом деле, ни приложение, ни тем более гид
 * узнать не могут — такого способа в Android нет.
 */
export type TaxiResult = 'app' | 'web' | 'failed';

export async function openTaxiTo(dest: TaxiDestination): Promise<TaxiResult> {
  const me = await coordsQuickly();
  const query = params(dest, me);

  try {
    await Linking.openURL(`yandextaxi://route?${query}`);
    return 'app';
  } catch {
    /* приложения нет на телефоне — уходим на веб-ссылку */
  }

  try {
    await Linking.openURL(`https://3.redirect.appmetrica.yandex.com/route?${query}`);
    return 'web';
  } catch {
    return 'failed';
  }
}
