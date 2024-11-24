use std::ops::AddAssign;

use crate::image::{BGRImage, Pixel};
const KEY_COLORS: [Pixel; 1] = [Pixel {
    pixel: &[225, 225, 225],
}];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
struct Block {
    left: usize,
    top: usize,
    right: usize,
    bottom: usize,
}
impl Ord for Block {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.top.cmp(&other.top)
    }
}
impl PartialOrd for Block {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}
impl AddAssign for Block {
    fn add_assign(&mut self, other: Self) {
        self.left = self.left.min(other.left);
        self.top = self.top.min(other.top);
        self.right = self.right.max(other.right);
        self.bottom = self.bottom.max(other.bottom);
    }
}
struct BlockedImage {
    rec: Vec<Vec<bool>>,
    blocks: Vec<Block>,
    b: Vec<Block>,
    fa: Vec<usize>,
    width: usize,
    height: usize,
}
impl BlockedImage {
    fn new(width: usize, height: usize) -> Self {
        Self {
            rec: vec![vec![false; width]; height],
            blocks: vec![],
            b: vec![Block::default(); width * height],
            fa: vec![0; width * height],
            width,
            height,
        }
    }
    fn init(&mut self, image: &BGRImage) {
        for (y, row) in self.rec.iter_mut().enumerate() {
            for (x, cell) in row.iter_mut().enumerate() {
                *cell = image.get_pixel(y, x).is_key_color(&KEY_COLORS, 50.0);
            }
        }
        for y in 0..self.height {
            for x in 0..self.width {
                let index = self.get_index(y, x);
                self.b[index] = Block {
                    left: x,
                    top: y,
                    right: x,
                    bottom: y,
                };
                self.fa[index] = index;
                if y > 0 && self.rec[y - 1][x] {
                    self.merge(index, self.get_index(y - 1, x));
                }
                if x > 0 && self.rec[y][x - 1] {
                    self.merge(index, self.get_index(y, x - 1));
                }
            }
        }
        for i in 0..self.width * self.height {
            if self.fa[i] == i && self.b[i].left != self.b[i].right {
                self.blocks.push(self.b[i]);
            }
        }
    }
    fn get_index(&self, y: usize, x: usize) -> usize {
        y * self.width + x
    }
    fn merge(&mut self, a: usize, b: usize) {
        let a = self.find(a);
        let b = self.find(b);
        if a == b {
            return;
        }
        let i = self.b[b];
        self.b[a] += i;
        self.fa[b] = a;
    }
    fn find(&mut self, x: usize) -> usize {
        let fa = &mut self.fa;
        let mut x = x;
        while fa[x] != x {
            fa[x] = fa[fa[x]];
            x = fa[x];
        }
        x
    }
}

type CorppedImage = Vec<Vec<bool>>;

#[allow(clippy::collapsible_else_if)]
pub fn recognize_map(image: &BGRImage) -> char {
    let mut blocked_image = BlockedImage::new(image.get_width(), image.get_height());
    blocked_image.init(image);
    blocked_image.blocks.sort();
    let mut corpped_img: CorppedImage = vec![];
    let block = blocked_image.blocks[0];
    for y in block.top..block.bottom {
        corpped_img.push(vec![]);
        for x in block.left..block.right {
            let index = blocked_image.get_index(y, x);
            let find = blocked_image.find(index);
            let var_name = blocked_image.b[find] == block;
            let col = blocked_image.rec[y][x] && (var_name);
            corpped_img[y - block.top].push(col);
        }
    }

    const INV_COUNT_LIMIT: i32 = 2;
    let line_col_rev = scan_col_rev(&corpped_img);
    let line_row_rev = scan_row_rev(&corpped_img);
    let line_row = scan_row(&corpped_img);

    let row_inv_count = line_row_rev.iter().filter(|&&x| x).count() as i32;
    let col_inv_count = line_col_rev.iter().filter(|&&x| x).count() as i32;

    if row_inv_count > INV_COUNT_LIMIT {
        if col_inv_count > INV_COUNT_LIMIT {
            const ACCEPTED_LENGTH_LIMIT: i32 = 2;
            let mut last = 0;
            let mut seg_count = 0;
            let mut type_val = -1;
            let start_with = line_row_rev[0];

            for &x in &line_row_rev {
                if type_val == -1 || x != (type_val != 0) {
                    if last >= ACCEPTED_LENGTH_LIMIT {
                        seg_count += 1;
                    }
                    last = 1;
                    type_val = x as i32;
                } else {
                    last += 1;
                }
            }
            if last >= ACCEPTED_LENGTH_LIMIT {
                seg_count += 1;
            }
            match seg_count {
                3 => {
                    if start_with {
                        'H'
                    } else {
                        'D'
                    }
                }
                4 => 'A',
                5 => {
                    const BC_COL_INV_LIMIT: i32 = 15;

                    if col_inv_count > BC_COL_INV_LIMIT {
                        'C'
                    } else {
                        'B'
                    }
                }
                6 | 7 => 'G',
                _ => '0',
            }
        } else {
            'H'
        }
    } else {
        if col_inv_count > INV_COUNT_LIMIT {
            let mut min_size = 100;
            let mut count = 0;
            const LIMIT: i32 = 18;

            for &x in &line_row {
                if x > 2 {
                    min_size = min_size.min(x);
                }
            }
            for &x in &line_row {
                if x > (1.5 * min_size as f32) as i32 {
                    count += 1;
                }
            }
            if count >= LIMIT {
                'E'
            } else {
                'F'
            }
        } else {
            const LENGTH_DIFF_LIMIT: i32 = 3;
            let mut min_size = 100;
            let mut max_size = 0;

            for &x in &line_row {
                if x > 2 {
                    min_size = min_size.min(x);
                    max_size = max_size.max(x);
                }
            }

            if max_size - min_size > LENGTH_DIFF_LIMIT {
                'J'
            } else {
                'I'
            }
        }
    }
}

#[allow(clippy::needless_range_loop)]
fn scan_row_rev(img: &CorppedImage) -> Vec<bool> {
    let mut res = vec![];
    let row = img.len();
    let col = img[0].len();
    for i in 0..row {
        let mut sum = 0;
        let mut exist = false;
        let mut closed = false;
        for j in 0..col {
            exist |= img[i][j];
            sum += (exist && !img[i][j]) as i32;
            closed |= sum != 0 && img[i][j];
        }
        res.push(sum > 0 && closed);
    }
    res
}

#[allow(clippy::needless_range_loop)]
fn scan_col_rev(img: &CorppedImage) -> Vec<bool> {
    let mut res = vec![];
    let row = img.len();
    let col = img[0].len();
    for j in 0..col {
        let mut sum = 0;
        let mut exist = false;
        let mut closed = false;
        for i in 0..row {
            exist |= img[i][j];
            sum += (exist && !img[i][j]) as i32;
            closed |= sum != 0 && img[i][j];
        }
        res.push(sum > 0 && closed);
    }
    res
}

#[allow(clippy::needless_range_loop)]
fn scan_row(img: &CorppedImage) -> Vec<i32> {
    let mut res = vec![];
    let row = img.len();
    let col = img[0].len();
    for i in 0..row {
        let mut sum = 0;
        for j in 0..col {
            sum += img[i][j] as i32;
        }
        res.push(sum);
    }
    res
}
