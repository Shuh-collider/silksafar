/** Геолокация пользователя — одна точка входа на всё приложение.
 *
 * Экраны не дёргают expo-location напрямую (кроме карты, где нужна ещё и
 * реакция на отказ), а зовут getMyCoords(): он сам спрашивает разрешение и
 * возвращает null, если пользователь отказал или координаты не пришли.
 * Решение, что показать вместо координат, принимает экран — тут никаких
 * алертов, чтобы функцию можно было звать в фоне.
 */

import * as Location from 'expo-location';
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface MyCoords {
  lat: number;
  lng: number;
}

const LAST_COORDS_KEY = 'last_known_coords';

/** Последние координаты с прошлого запуска. Нужны, чтобы показать погоду
 *  нужного города сразу, не дожидаясь GPS (и вообще без сети). */
export async function getCachedCoords(): Promise<MyCoords | null> {
  try {
    const raw = await AsyncStorage.getItem(LAST_COORDS_KEY);
    return raw ? (JSON.parse(raw) as MyCoords) : null;
  } catch {
    return null;
  }
}

/** Текущие координаты или null (отказ в разрешении / GPS молчит). */
export async function getMyCoords(): Promise<MyCoords | null> {
  try {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') return null;
    const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    AsyncStorage.setItem(LAST_COORDS_KEY, JSON.stringify(coords)).catch(() => {});
    return coords;
  } catch {
    return null;
  }
}

/** Расстояние между точками в километрах (формула гаверсинуса).
 *  Нужно, чтобы не переспрашивать название города, пока юзер не уехал далеко. */
export function distanceKm(a: MyCoords, b: MyCoords): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(h));
}
