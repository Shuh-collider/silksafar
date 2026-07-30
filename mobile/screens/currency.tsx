import React, { useEffect, useMemo, useState } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  SafeAreaView,
  StatusBar,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { useAuth } from '@/auth/auth-context';
import { CurrencyRate, api } from '@/lib/api';
import { useI18n } from '@/i18n/i18n-context';

const CURRENCY_CACHE_KEY = 'home_currency_cache';

const FLAGS: Record<string, string> = {
  UZS: '🇺🇿',
  USD: '🇺🇸',
  EUR: '🇪🇺',
  RUB: '🇷🇺',
  CNY: '🇨🇳',
};

/** Сум в списке курсов ЦБ не приходит — он и есть база. Добавляем его сами
 *  с курсом 1, чтобы конвертация считалась одной формулой для всех пар. */
const UZS: CurrencyRate = { code: 'UZS', rate: 1, diff: 0, date: '' };

/** Разделяем тысячи неразрывным пробелом: суммы в сумах длинные (12 700 000). */
function formatMoney(value: number): string {
  if (!isFinite(value)) return '—';
  const decimals = value !== 0 && Math.abs(value) < 100 ? 2 : 0;
  return value.toLocaleString('ru-RU', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Разбор того, что в поле. Считаться должно и с уже отформатированной строкой:
 *  соседнее поле показывает «1 270 000», и пользователь может начать править
 *  именно его — значит пробелы (в т.ч. неразрывные) и запятую надо принимать. */
function parseMoney(text: string): number {
  // \s в JS покрывает и неразрывный пробел — именно его ставит toLocaleString.
  return parseFloat(text.replace(/\s/g, '').replace(',', '.'));
}

export default function CurrencyScreen() {
  const { token } = useAuth();
  const { t } = useI18n();

  const [rates, setRates] = useState<CurrencyRate[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);

  const [from, setFrom] = useState('USD');
  const [to, setTo] = useState('UZS');

  // Считать надо в обе стороны: «сколько сумов за $100» и «сколько долларов на
  // 1 000 000 сум». Поэтому храним текст обоих полей и то, какое правили
  // последним — оно источник, второе всегда пересчитывается из него.
  const [fromText, setFromText] = useState('100');
  const [toText, setToText] = useState('');
  const [edited, setEdited] = useState<'from' | 'to'>('from');

  // Как и на главной: сначала показываем последние сохранённые курсы (работает
  // без сети), затем в фоне обновляем. Ключ кэша общий с главной — данные те же.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const cached = await AsyncStorage.getItem(CURRENCY_CACHE_KEY);
      if (cached && !cancelled) {
        try {
          setRates(JSON.parse(cached));
          setLoading(false);
        } catch {}
      }
      if (!token) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const fresh = await api.currency(token);
        if (cancelled) return;
        setRates(fresh);
        setErrorText(null);
        AsyncStorage.setItem(CURRENCY_CACHE_KEY, JSON.stringify(fresh)).catch(() => {});
      } catch {
        if (!cancelled && !cached) setErrorText(t('cur.error'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const all = useMemo(() => (rates ? [UZS, ...rates] : []), [rates]);
  const rateOf = (code: string) => all.find((r) => r.code === code)?.rate ?? 0;

  // Курсы ЦБ — «сколько сумов за 1 единицу», поэтому любая пара считается
  // через сум одной формулой, в какую бы сторону ни считали.
  const convert = (value: number, src: string, dst: string) =>
    rateOf(dst) === 0 ? null : (value * rateOf(src)) / rateOf(dst);

  const sourceValue = parseMoney(edited === 'from' ? fromText : toText);
  const computed = isNaN(sourceValue)
    ? null
    : edited === 'from'
      ? convert(sourceValue, from, to)
      : convert(sourceValue, to, from);

  const computedText = computed == null ? '' : formatMoney(computed);
  // Поле, которое правят, показывает ровно то, что набрали, — иначе курсор
  // будет прыгать на каждом символе. Второе показывает пересчёт.
  const shownFrom = edited === 'from' ? fromText : computedText;
  const shownTo = edited === 'to' ? toText : computedText;

  const oneUnit = rateOf(to) === 0 ? null : rateOf(from) / rateOf(to);

  // Меняем валюты местами вместе со значениями: было «100 USD → 1 270 000 UZS»,
  // стало «1 270 000 UZS → 100 USD» — то же самое, только наоборот.
  const swap = () => {
    const newTop = shownTo;
    setFrom(to);
    setTo(from);
    setFromText(newTop);
    setEdited('from');
  };

  const renderPicker = (selected: string, onSelect: (code: string) => void) => (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.pickerRow}>
      {all.map((r) => (
        <TouchableOpacity
          key={r.code}
          style={[styles.chip, r.code === selected && styles.chipActive]}
          onPress={() => onSelect(r.code)}
        >
          <Text style={[styles.chipText, r.code === selected && styles.chipTextActive]}>
            {FLAGS[r.code] ?? ''} {r.code}
          </Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#090B11" />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
          {loading && (
            <View style={styles.centerBox}>
              <ActivityIndicator size="large" color="#3B82F6" />
            </View>
          )}

          {!loading && errorText && (
            <View style={styles.centerBox}>
              <Text style={styles.errorText}>{errorText}</Text>
            </View>
          )}

          {!loading && !errorText && rates && rates.length > 0 && (
            <>
              <View style={styles.card}>
                <Text style={styles.fieldLabel}>{t('cur.amount')}</Text>
                <TextInput
                  style={styles.input}
                  value={shownFrom}
                  onChangeText={(v) => {
                    setFromText(v);
                    setEdited('from');
                  }}
                  keyboardType="numeric"
                  placeholder="0"
                  placeholderTextColor="#4B5563"
                  selectTextOnFocus
                />
                {renderPicker(from, setFrom)}
              </View>

              <TouchableOpacity style={styles.swapButton} onPress={swap} activeOpacity={0.7}>
                <Text style={styles.swapIcon}>⇅</Text>
              </TouchableOpacity>

              <View style={styles.card}>
                <Text style={styles.fieldLabel}>{t('cur.result')}</Text>
                <TextInput
                  style={[styles.input, styles.inputResult]}
                  value={shownTo}
                  onChangeText={(v) => {
                    setToText(v);
                    setEdited('to');
                  }}
                  keyboardType="numeric"
                  placeholder="0"
                  placeholderTextColor="#4B5563"
                  selectTextOnFocus
                />
                {renderPicker(to, setTo)}
              </View>

              {oneUnit != null && (
                <Text style={styles.rateLine}>
                  {t('cur.rateLine', { from, value: formatMoney(oneUnit), to })}
                </Text>
              )}

              <Text style={styles.sectionTitle}>{t('cur.ratesTitle')}</Text>
              {rates.map((r) => (
                <View key={r.code} style={styles.rateRow}>
                  <Text style={styles.rateFlag}>{FLAGS[r.code] ?? ''}</Text>
                  <View style={styles.rateNameWrapper}>
                    <Text style={styles.rateCode}>{r.code}</Text>
                    <Text style={styles.rateName}>{t(`cur.name.${r.code}`)}</Text>
                  </View>
                  <View style={styles.rateValueWrapper}>
                    <Text style={styles.rateValue}>{formatMoney(r.rate)}</Text>
                    {r.diff !== 0 && (
                      <Text style={[styles.rateDiff, { color: r.diff > 0 ? '#F87171' : '#34D399' }]}>
                        {r.diff > 0 ? '▲' : '▼'} {formatMoney(Math.abs(r.diff))}
                      </Text>
                    )}
                  </View>
                </View>
              ))}

              {rates[0]?.date ? (
                <Text style={styles.updated}>{t('cur.updated', { date: rates[0].date })}</Text>
              ) : null}
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#070814',
  },
  flex: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  centerBox: {
    paddingVertical: 60,
    alignItems: 'center',
  },
  errorText: {
    color: '#9CA3AF',
    fontSize: 14,
    textAlign: 'center',
    paddingHorizontal: 20,
  },
  card: {
    backgroundColor: '#0F1123',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#232448',
    padding: 16,
  },
  fieldLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#9CA3AF',
    textTransform: 'uppercase',
    marginBottom: 6,
  },
  input: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#FFFFFF',
    padding: 0,
    marginBottom: 12,
  },
  // Нижнее поле тоже редактируемое, но зелёное — чтобы читалось как результат.
  inputResult: {
    color: '#34D399',
  },
  pickerRow: {
    marginHorizontal: -4,
  },
  chip: {
    backgroundColor: '#151833',
    borderWidth: 1,
    borderColor: '#232B5E',
    borderRadius: 20,
    paddingVertical: 7,
    paddingHorizontal: 14,
    marginHorizontal: 4,
  },
  chipActive: {
    backgroundColor: '#1E3A5F',
    borderColor: '#3B82F6',
  },
  chipText: {
    color: '#9CA3AF',
    fontSize: 13,
    fontWeight: '600',
  },
  chipTextActive: {
    color: '#FFFFFF',
  },
  swapButton: {
    alignSelf: 'center',
    backgroundColor: '#1E3A5F',
    borderWidth: 1,
    borderColor: '#3B82F6',
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: 10,
  },
  swapIcon: {
    fontSize: 22,
    color: '#FFFFFF',
    lineHeight: 26,
  },
  rateLine: {
    fontSize: 13,
    color: '#9CA3AF',
    textAlign: 'center',
    marginTop: 14,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#9CA3AF',
    textTransform: 'uppercase',
    marginTop: 24,
    marginBottom: 10,
  },
  rateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0F1123',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#232448',
    paddingVertical: 12,
    paddingHorizontal: 14,
    marginBottom: 8,
  },
  rateFlag: {
    fontSize: 20,
    marginRight: 12,
  },
  rateNameWrapper: {
    flex: 1,
  },
  rateCode: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FFFFFF',
  },
  rateName: {
    fontSize: 11,
    color: '#6B7280',
    marginTop: 2,
  },
  rateValueWrapper: {
    alignItems: 'flex-end',
  },
  rateValue: {
    fontSize: 15,
    fontWeight: '600',
    color: '#E5E7EB',
  },
  rateDiff: {
    fontSize: 11,
    marginTop: 2,
  },
  updated: {
    fontSize: 12,
    color: '#6B7280',
    textAlign: 'center',
    marginTop: 12,
  },
});
