use strum_macros::{AsRefStr, EnumIter, FromRepr};
#[allow(clippy::upper_case_acronyms)]
#[derive(Debug, Clone, Copy, FromRepr, AsRefStr, EnumIter)]
pub enum VesselType {
    BB,  //战列
    BBV, //航战
    BC,  //战巡
    BBG, //导战
    CBG, //大巡

    CV,  //航母
    CVL, //轻母
    AV,  //装母

    CA,  //重巡
    CL,  //轻巡
    CLT, //雷巡
    CAV, //航巡
    KP,  //导巡
    CG,  //防巡

    BM, //重炮

    DD,   //驱逐
    ASDG, //导驱
    AADG, //防驱

    SS, //潜艇
    SC, //炮潜

    AP,       //补给
    Elite,    //旗舰
    Fortess,  //要塞
    Port,     //港口
    Airfield, //机场
    NotDef,   //调谐

    NO, //无舰船
}

pub enum 舰船种类 {
    战列,
    航战,
    战巡,
    导战,
    大巡,

    航母,
    轻母,
    装母,

    重巡,
    轻巡,
    雷巡,
    航巡,
    导巡,
    防巡,

    重炮,

    驱逐,
    导驱,
    防驱,

    潜艇,
    炮潜,

    补给,
    旗舰,
    要塞,
    港口,
    机场,
    谐调,

    无舰船,
}

#[cfg(test)]
mod tests {
    use strum::IntoEnumIterator;

    use super::*;

    #[test]
    fn test_vessel_type() {
        assert_eq!(VesselType::BB as u8, 0);
        assert_eq!(VesselType::BBV as u8, 1);
        assert_eq!(VesselType::BC as u8, 2);
        assert_eq!(VesselType::BBG as u8, 3);
        assert_eq!(VesselType::CBG as u8, 4);
        assert_eq!(VesselType::CV as u8, 5);
        assert_eq!(VesselType::CVL as u8, 6);
        assert_eq!(VesselType::AV as u8, 7);
        assert_eq!(VesselType::CA as u8, 8);
        assert_eq!(VesselType::CL as u8, 9);
        assert_eq!(VesselType::CLT as u8, 10);
        assert_eq!(VesselType::CAV as u8, 11);
        assert_eq!(VesselType::KP as u8, 12);
        assert_eq!(VesselType::CG as u8, 13);
        assert_eq!(VesselType::BM as u8, 14);
        assert_eq!(VesselType::DD as u8, 15);
        assert_eq!(VesselType::ASDG as u8, 16);
        assert_eq!(VesselType::AADG as u8, 17);
        assert_eq!(VesselType::SS as u8, 18);
        assert_eq!(VesselType::SC as u8, 19);
        assert_eq!(VesselType::AP as u8, 20);
        assert_eq!(VesselType::Elite as u8, 21);
        assert_eq!(VesselType::Fortess as u8, 22);
        assert_eq!(VesselType::Port as u8, 23);
        assert_eq!(VesselType::Airfield as u8, 24);
        assert_eq!(VesselType::NotDef as u8, 25);
        assert_eq!(VesselType::NO as u8, 26);
    }

    #[test]
    fn test_iter() {
        for i in VesselType::iter() {
            println!("{:?}", i);
        }
    }
}
