import React from 'react';
import { StyleSheet, View } from 'react-native';

/** Пин-«капля», как на картах. Рисуется на View, без иконочных шрифтов и SVG:
 *  в проекте нет ни `@expo/vector-icons`, ни `react-native-svg`, а тянуть их
 *  ради одной иконки — лишняя зависимость и лишняя пересборка.
 *
 *  Форма — квадрат с тремя скруглёнными углами, повёрнутый на -45°: острый
 *  угол оказывается ровно внизу. Размеры контейнера считаются от диагонали
 *  (сторона × √2), иначе повёрнутый квадрат вылезает за свои границы.
 */
interface PinIconProps {
  size?: number;
  color?: string;
  /** Цвет «дырки» в центре пина — должен совпадать с фоном под иконкой,
   *  иначе кружок будет заметен как чужеродное пятно. */
  holeColor?: string;
}

export function PinIcon({ size = 14, color = '#3B82F6', holeColor = '#0F1123' }: PinIconProps) {
  const box = size * 1.414; // диагональ квадрата — столько места он займёт после поворота
  const offset = (box - size) / 2;
  const hole = size * 0.34;

  return (
    <View style={{ width: box, height: box }}>
      <View
        style={{
          position: 'absolute',
          left: offset,
          top: offset,
          width: size,
          height: size,
          backgroundColor: color,
          borderTopLeftRadius: size / 2,
          borderTopRightRadius: size / 2,
          borderBottomRightRadius: size / 2,
          borderBottomLeftRadius: 0,
          transform: [{ rotate: '-45deg' }],
        }}
      />
      <View
        style={[
          styles.hole,
          {
            width: hole,
            height: hole,
            borderRadius: hole / 2,
            left: (box - hole) / 2,
            top: (box - hole) / 2,
            backgroundColor: holeColor,
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  hole: {
    position: 'absolute',
  },
});
