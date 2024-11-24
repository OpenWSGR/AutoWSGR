mod image;
mod interface;
mod locator;
mod recognize_enemy;
mod recognize_map;

use image::BGRImage;
use interface::{Interface, RecognizeEnemyInput, WrappedPixels};

use std::ffi::{c_char, c_int, c_void};

/// # Safety
/// The output pointer must be NOT freed by caller
///
/// call free_arr to free the output string
///
/// return -1 if failed
///
/// # Usage
///
/// locate the blue textbox and return a array contains the position of the textboxes
///
/// e.g. [[0, 1], [2, 3], [4, 5]]
#[no_mangle]
pub unsafe extern "C" fn locate(input: *const c_void, output: *mut c_int) -> c_int {
    let image = BGRImage::from_wrapped_pixels(WrappedPixels::from_raw(input));
    let result = locator::locate(&image);
    if result.is_empty() || result.len() >= 32 {
        return -1;
    }
    let len = result.len();
    output.copy_from_nonoverlapping(result.as_ptr() as *const c_int, len);
    len as c_int
}

/// # Safety
/// The output pointer must be NOT freed by caller
///
/// call free_str to free the output string
///
/// return -1 if failed
///
/// # Usage
///
/// recognize them when enemys were spotted and return a string
///
/// e.g. "DD SS NO NO NO NO"

#[no_mangle]
pub unsafe extern "C" fn recognize_enemy(input: *const c_void, output: *mut c_char) -> c_int {
    let input = RecognizeEnemyInput::from_raw(input);
    let result = recognize_enemy::recognize_enemy(
        &input.images,
        &recognize_enemy::templates::Template::init_templates(),
    );

    output.copy_from(result.as_ptr() as *const c_char, result.len());
    0
}

/// # Safety
/// no return pointer. Safe
///
/// return -1 if failed
///
/// # Usage
///
/// process decisive_battle map image for recognize
///
/// e.g. 'J'
#[no_mangle]
pub unsafe extern "C" fn recognize_map(input: *const c_void) -> c_char {
    let image = BGRImage::from_wrapped_pixels(WrappedPixels::from_raw(input));
    let result = recognize_map::recognize_map(&image);
    result as c_char
}
