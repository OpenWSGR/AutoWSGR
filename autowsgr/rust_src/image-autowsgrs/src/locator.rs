use crate::image::{BGRImage, Pixel};

const KEY_COLORS: [Pixel; 3] = [
    Pixel {
        pixel: &[162, 98, 18],
    },
    Pixel {
        pixel: &[173, 103, 17],
    },
    Pixel {
        pixel: &[196, 116, 16],
    },
];

pub fn locate(image: &BGRImage) -> Vec<i32> {
    let width = image.get_width();
    let height = image.get_height();

    // mark key color
    let mut is_key_map = vec![vec![false; width]; height];
    for (y, row) in is_key_map.iter_mut().enumerate() {
        for (x, is_key) in row.iter_mut().enumerate() {
            let pixel = image.get_pixel(y, x);
            *is_key = pixel.is_key_color(&KEY_COLORS, 20.0);
        }
    }

    // make segments
    let mut segments = vec![vec![]; height];
    for y in 1..height {
        let mut last_key = -1;
        for x in 1..width {
            if is_key_map[y][x] {
                if !is_key_map[y][x - 1] {
                    last_key = x as i32;
                }
            } else if is_key_map[y][x - 1] && x as i32 - last_key > 10 {
                segments[y].push((last_key, x as i32 - 1));
            }
        }
    }
    // validate lines
    let mut is_line_valid = vec![false; height];
    for y in 1..height {
        if segments[y].is_empty() {
            continue;
        }
        let mut cnt1 = 0;
        let mut cnt2 = 0;
        for i in -8..=-1 {
            if 0 < y as i32 + i && y as i32 + i < height as i32 {
                cnt1 += cmp_line(&segments[y], &segments[(y as i32 + i) as usize]);
            }
        }
        for i in 1..=8 {
            if 0 < y as i32 + i && y as i32 + i < height as i32 {
                cnt2 += cmp_line(&segments[y], &segments[(y as i32 + i) as usize]);
            }
        }
        if i32::max(cnt1, cnt2) >= 6 {
            is_line_valid[y] = true;
        }
    }
    // make result
    let mut result = vec![];
    let mut lst = -1;
    for (row, is_line_valid) in is_line_valid.iter().enumerate() {
        if *is_line_valid {
            if lst == -1 {
                lst = row as i32;
            }
        } else if lst != -1 {
            result.push(lst);
            result.push(row as i32);
            lst = -1;
        }
    }

    result
}

/// wtf
fn cmp_line(line1: &[(i32, i32)], line2: &[(i32, i32)]) -> i32 {
    match line1.is_empty() {
        true => 0,
        false => match line2.is_empty() {
            true => 0,
            false => 1,
        },
    }
    // for s1 in line1 {
    //     let mut flag = false;
    //     for s2 in line2 {
    //         if i32::min(i32::abs(s1.0 - s2.0), i32::abs(s1.1 - s2.1)) <= 2 {
    //             flag = true;
    //             break;
    //         }
    //     }
    //     if !flag {
    //         return 0;
    //     }
    // }
    // 1
}
