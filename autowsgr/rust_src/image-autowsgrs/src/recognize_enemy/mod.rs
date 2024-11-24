pub mod character_image;
pub mod templates;

use character_image::{CharacterImage, MatchMethod};
use templates::Template;

pub const WIDTH: usize = 32;
pub const HEIGHT: usize = 16;
const ENDWITH_巡: &[&str; 6] = &["CA", "CL", "CAV", "CLT", "CBG", "BC"];
const ENDWITH_母: &[&str; 3] = &["CV", "AV", "CVL"];
const STARTWITH_战: &[&str; 2] = &["BB", "BC"];
const STARTWITH_轻: &[&str; 2] = &["CL", "CVL"];

pub fn recognize_enemy(images: &[CharacterImage], templates: &[Template]) -> String {
    let mut string = String::new();

    for image in images {
        let mut min = &templates[0];
        for current in templates.iter().skip(1) {
            let category = check_category(min, current);
            let method = match category {
                Category::Endwith巡 | Category::Endwith母 => MatchMethod::First,
                Category::Startwith战 | Category::Startwith轻 => MatchMethod::Last,
                Category::None => MatchMethod::All,
            };
            let diff_current = image.calc_image_diffreance(current, method);
            let diff_min = image.calc_image_diffreance(min, method);
            if diff_current < diff_min {
                min = current;
            }
        }
        string.push_str(min.ship_type.as_ref());
        string.push(' ');
    }

    string
}

#[derive(Debug)]
enum Category {
    Endwith巡,
    Endwith母,
    Startwith战,
    Startwith轻,
    None,
}
fn check_category(a: &Template, b: &Template) -> Category {
    if ENDWITH_巡.contains(&a.ship_type.as_ref()) && ENDWITH_巡.contains(&b.ship_type.as_ref()) {
        return Category::Endwith巡;
    }
    if ENDWITH_母.contains(&a.ship_type.as_ref()) && ENDWITH_母.contains(&b.ship_type.as_ref()) {
        return Category::Endwith母;
    }
    if STARTWITH_战.contains(&a.ship_type.as_ref()) && STARTWITH_战.contains(&b.ship_type.as_ref())
    {
        return Category::Startwith战;
    }
    if STARTWITH_轻.contains(&a.ship_type.as_ref()) && STARTWITH_轻.contains(&b.ship_type.as_ref())
    {
        return Category::Startwith轻;
    }
    Category::None
}
