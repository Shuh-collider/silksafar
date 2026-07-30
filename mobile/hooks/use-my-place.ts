/** «Где сейчас пользователь» — координаты + название города.
 *
 * Один хук на главную и на погоду, чтобы разрешение спрашивалось одинаково и
 * название города не запрашивалось дважды. Работает офлайн-устойчиво: сначала
 * отдаёт координаты и название с прошлого запуска, потом уточняет.
 */

import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { useAuth } from '@/auth/auth-context';
import { api } from '@/lib/api';
import { useI18n } from '@/i18n/i18n-context';
import { MyCoords, distanceKm, getCachedCoords, getMyCoords } from '@/utils/location';

const PLACE_CACHE_KEY = 'my_place_cache';

// Пока пользователь не уехал дальше этого расстояния, название города берём из
// кэша: у Nominatim лимит ~1 запрос/сек, а город на таком расстоянии не меняется.
const REUSE_NAME_WITHIN_KM = 10;

interface PlaceCache extends MyCoords {
  city: string;
  /** Язык, на котором сохранено название. Без него после смены языка
   *  интерфейса подпись осталась бы на прежнем — кэш бы её «залипил». */
  lang: string;
}

export type LocationStatus = 'loading' | 'ready' | 'denied';

export function useMyPlace() {
  const { token } = useAuth();
  const { lang } = useI18n();
  const [coords, setCoords] = useState<MyCoords | null>(null);
  const [cityName, setCityName] = useState<string | null>(null);
  const [status, setStatus] = useState<LocationStatus>('loading');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const cached = await getCachedCoords();
      if (cached && !cancelled) {
        setCoords(cached);
        setStatus('ready');
      }
      const fresh = await getMyCoords();
      if (cancelled) return;
      if (fresh) {
        setCoords(fresh);
        setStatus('ready');
      } else if (!cached) {
        setStatus('denied');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!coords) return;
    let cancelled = false;
    (async () => {
      let cache: PlaceCache | null = null;
      try {
        const raw = await AsyncStorage.getItem(PLACE_CACHE_KEY);
        cache = raw ? (JSON.parse(raw) as PlaceCache) : null;
      } catch {}
      if (cache && cache.lang === lang && distanceKm(cache, coords) < REUSE_NAME_WITHIN_KM) {
        if (!cancelled) setCityName(cache.city);
        return;
      }
      if (!token) return;
      try {
        const res = await api.reverseGeocode(coords.lat, coords.lng, token, lang);
        if (cancelled || !res.city) return;
        setCityName(res.city);
        AsyncStorage.setItem(
          PLACE_CACHE_KEY,
          JSON.stringify({ lat: coords.lat, lng: coords.lng, city: res.city, lang }),
        ).catch(() => {});
      } catch {
        /* нет сети — останется прежнее название или ничего */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [coords?.lat, coords?.lng, token, lang]);

  return { coords, cityName, status };
}
