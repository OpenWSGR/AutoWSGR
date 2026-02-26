"""主页面 UI 控制层。

使用方式::

    from autowsgr.ui.main_page import MainPage

    page = MainPage(ctrl)
    page.navigate_to(MainPage.Target.SORTIE)
"""

from .controller import MainPage


__all__ = ['MainPage']
