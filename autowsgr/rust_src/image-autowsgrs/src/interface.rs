use std::ffi::c_void;

use crate::recognize_enemy::character_image::CharacterImage;
pub struct RecognizeEnemyInput {
    pub images: Vec<CharacterImage>,
}

pub struct WrappedPixels<'i> {
    pub width: usize,
    pub height: usize,
    pub channels: usize,
    pub pixels: &'i [u8],
}

pub trait Interface {
    /// # Safety
    /// 非常滴安全,非常滴可靠口牙
    unsafe fn from_raw(raw: *const c_void) -> Self;
}
impl Interface for WrappedPixels<'_> {
    /// # Layout of raw:
    ///
    /// usize[w, h, c, pixels_p[u8]]
    unsafe fn from_raw(raw: *const c_void) -> Self {
        let raw = raw as *const usize;
        let width = *raw.offset(0);
        let height = *raw.offset(1);
        let channels = *raw.offset(2);
        let pixels_p = *raw.offset(3) as *const u8;
        let pixels = std::slice::from_raw_parts(pixels_p, width * height * channels);
        WrappedPixels {
            width,
            height,
            channels,
            pixels,
        }
    }
}
impl Interface for RecognizeEnemyInput {
    /// # Layout of raw:
    ///
    /// usize[ templates_p[Template], image_count, images_p[usize[w, h, pixels_p[u8]]]]
    ///
    /// fail when height != HEIGHT || width != WIDTH
    unsafe fn from_raw(raw: *const c_void) -> Self {
        let raw = raw as *const usize;
        let image_count = *raw.offset(0);
        let images_p = *raw.offset(1) as *const usize;

        let mut images = Vec::with_capacity(image_count);
        for i in 0..image_count {
            let image = *images_p.add(i) as *const c_void;
            let image = WrappedPixels::from_raw(image);
            images.push(CharacterImage::from_wrapped_pixels(image));
        }
        Self { images }
    }
}
