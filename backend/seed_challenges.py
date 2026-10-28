"""Seeds this event's real, fully-written challenges (see _CONTENT below for
each one's actual title/task text). This file used to also seed ~36
placeholder landmark challenges with a literal "TBD" description — those
have been removed entirely (see the DELETE at the end of seed(), which drops
any challenge no longer listed in _CHALLENGES rather than just hiding it).

Every challenge's `description` defaults to a literal "TBD" placeholder if
it isn't in _CONTENT, so a new entry here is still playable as soon as its
reward/location are filled in, even before real content is written.
Exactly 3 start `pool_state='active'` — all `type='fixed'` (constant-value
reward) per the game's opening-pool rule; the rest start 'queued' and enter
play later via activate_initial_pool()/_refill_pool() in game_logic.py.

`seed()` is idempotent and upserts by `name` (see idx_challenges_name in
schema.sql). It deliberately never overwrites `pool_state` on conflict, so
redeploying mid-event never resets a challenge that's already gone
active/retired — only name/type/reward/location/content edits here take
effect. Runs automatically on every backend startup (see migrate.py).
"""
import json

TBD = "TBD"

# name -> (inner_title, description). Real/flavor title + team-facing task
# text, only revealed to a team once their attempt is approved to start (see
# routers/challenges.py). Any challenge whose name isn't listed here still
# gets the TBD/TBD placeholder. Keep any admin-only answer key OUT of here
# (description reaches the attempting team) — put it in a comment next to
# the challenge's entry in _CHALLENGES instead, or hand it to admins
# out-of-band; either way it must never round-trip through the DB/API.
_CONTENT: dict[str, tuple[str, str]] = {
    "台大二活任務": (
        "台大社團知多少",
        "限時10分鐘，請上去二活的8-10樓，去看二活的8-10樓有哪些各社辦，可以分工合作分頭行動。"
        "結束後回到此地（二活一樓門口），隨隊管理員將會講出7個社團的名字，你們要告訴他二活是否存在該社團的社辦。"
        "回答時請選一個人做為代表，其他人可以在旁邊幫忙討論，並且告訴他答案。"
        "回答時禁止看手機或是筆記。",
    ),
    "西門町任務": (
        "西門町任務：致二次元裡獨特的你",
        "高松燈（左圖，來自 BanG Dream! It's MyGO!!!!!）與天王寺璃奈"
        "（右圖，來自《LoveLive! 虹咲學園校園偶像同好會》）都是常被觀眾認為帶有自閉症特質的角色："
        "前者在語言表達上有困難，且有著特殊的執著與愛好（例如收集石頭）；"
        "後者則難以透過臉部展現情緒，因此她會用手繪的表情板告訴大家自己現在的心情，"
        "也曾面臨孤獨、難以交到朋友的處境。"
        "西門町是二次元動漫文化的聖地，請找到「高松燈」或「天王寺璃奈」任一位角色的周邊，"
        "價格300元（含）以內，把它買下來"
        "（活動結束後請把周邊轉交給主辦人，主辦人會給你錢）。"
        "周邊可為同人或是官方商品，但周邊上不得出現其他角色的圖案。",
    ),
    "建成圓環任務": (
        "許願圓環：喊出你的極限數字",
        "恭喜你們來到了建成圓環！這裡曾經真的是一個圓環，也是老台北最有名的小吃聚集地之一，"
        "但原本的圓環如今已經被拆除了。既然圓環已經不在，就由你們來把它圍回來吧——請大家圍成一個圓，依照逆時針的方向輪流數數，並且決定好誰先，從1數到你們喊出的目標數字"
        "（須介於30~100之間，開始任務前自行決定）。只是現在星雨是68期，所以遇到6的倍數、8的倍數，"
        "或是數字中包含6或8，請改成拍手而不把數字數出來。如果成功數到你們喊出的數字，就獲得「目標數字 × 0.3」的代幣（四捨五入），"
        "但只要有一個人搞砸，或是停頓超過5秒鐘，就任務失敗，一枚都拿不到。",
    ),
    "台北地下街任務": (
        "步步為贏：丈量地下街",
        "Y區地下街是台北市最繁華的地下街之一，裡面有許多動漫遊戲相關的店家，也有販售東南亞異國料理。"
        "現在，直到任務結束為止都禁止使用手機與網路，也禁止問其他人。請測量台北地下街的總長，"
        "誤差需在100公尺（含）以內。",
    ),
    "葫洲站任務": (
        "巷口的牛肉麵回憶",
        "主辦人的家就在葫洲站附近。雖然主辦人總是笑稱內湖是美食沙漠，但這裡也還是有很多從小吃到大的好滋味。"
        "請在附近找到一間有賣牛肉麵的平價台式早午餐店，並在店家前面拍合照！"
        "只有一次機會，如果找錯家就算任務失敗。",
    ),
    "美麗華任務": (
        "接力爬樓梯",
        "歡迎來到美麗華，這裡有著台灣最美的摩天輪之一。但主辦人同樣也很喜歡美麗華室外的樓梯，"
        "且從地面層沿著樓梯爬到最上面就能抵達摩天輪的所在處！所以，主辦人想讓你們親自體驗爬這座樓梯的感覺。"
        "這是一場接力賽：請先決定你們要完成幾趟樓梯往返，"
        "一趟是從地面層爬到摩天輪所在的樓層再回到地面，必須真的抵達那一層才能折返。"
        "**任務開始前請先決定好隊員的接力順序，開始之後不得更改。**"
        "所有人都跑完一輪之後，再從第一位開始輪下一輪，直到完成你們喊出的趟數。"
        "限時10分鐘，指定的趟數全部完成才算成功；只要有一趟沒跑完、有人跑錯順序，或是超過時間，任務失敗。",
    ),
    "頂埔站任務": (
        "月台上的六分鐘",
        "三鶯線是最近才剛通車的捷運線，但是實際去體驗過後，會發現他的車速既慢，班距也久，"
        "很常需要在月台上罰站6分鐘車才會來。因此，如果能夠精準預測候車時間的話，一定能減輕很多負擔吧！"
        "現在，請在板南線月台上小組內討論，猜一個時間（例如：3分30秒）。"
        "決定之後你們將一起走至三鶯線的驗票閘門旁，到的時候一開始看到的三鶯線發車等候時間，"
        "如果跟你們預測的時間誤差不超過1分鐘，就算是任務成功，否則就任務失敗！",
    ),
    "明曜百貨任務": (
        "東區裡的舞步傳說",
        "如圖，Dance Dance Revolution，是二十幾年前曾經風靡全球的跳舞街機遊戲，時至今日，此遊戲雖然風光不如以往，"
        "但仍有許多忠實熱忱的玩家，也有一些把這個遊戲當成運動或拿來減肥的玩家。台北市內還有數個地方有這個機台，"
        "而明曜百貨11樓就是其中之一。"
        "現在，請跟你的隨隊人員要6枚代幣，並實際遊玩此機台；如果有人在排隊，請照規矩排隊等候。"
        "遊玩一次總共是3首歌，前2首是練習，第3首才是正式的任務挑戰。"
        "你們必須在第3首歌開始之前宣告自己欲挑戰的等級（數字），"
        "並且選擇的歌曲曲名中必須含有「星」、「雨」、「star」或「rain」（英文大小寫不拘）。"
        "如果過關，可獲得「挑戰等級×3」的代幣；如果選錯歌曲或是沒有過關，則任務失敗。",
    ),
    "松山機場任務": (
        "看別人出國的下午",
        "大家應該都很想搭飛機出國玩吧！但很可惜，我們社遊沒有經費讓你們出國，"
        "但至少可以來松山機場欣賞別人出國。"
        "現在，請一個人拿手機，錄下一架飛機完整的起飛過程。"
        "錄下的影片必須至少包含：飛機在地上行走3秒鐘、飛機離地的瞬間，"
        "以及飛機在畫面上的高度超過視野前方的山脈。",
    ),
    "木柵機廠任務": (
        "猜猜下一班回家的是誰",
        "歡迎來到木柵機廠，這裡是文湖線捷運列車的其中一個家。"
        "現行文湖線營運中的列車共有兩種車型，分別是左圖的馬特拉列車（車號是2位數），"
        "以及右圖的龐巴迪列車（車號是3位數）。"
        "現在，請猜測下一列入庫／出庫的列車的車型，猜測必須在任何列車有動靜之前做出才算。"
        "如果失敗了可以等再猜下一列車的車型，直到成功為止。",
    ),
    "辛亥國小任務": (
        "七成的罰球線",
        "辛亥國小是少數擁有室外風雨籃球場的國小，並且假日開放一般民眾入場打球。"
        "我們沒辦法攜帶籃球給各位投籃，但你們可以用乒乓球投。"
        "台灣職業籃球聯盟的平均罰球命中率大概在70%左右，如果你們也能夠達成相同命中率的話，"
        "或許就可以當職籃球員了！"
        "請小組組員決定順序，並依此順序輪流在任意籃筐的罰球線投乒乓球，總共會投10球，"
        "如果進了7球就算任務成功，進不到7球就任務失敗。"
        "在宣告開始挑戰之前，你們可以自由練習並討論順序的策略。",
    ),
    "南港區民活動中心任務": (
        "啪——啪啪啪——",
        "歡迎來到南港區民活動中心，這裡是星雨上一期青假早上認識活動以及教案的進行場地。"
        "其中，教案組設計的其中一個活動就是摩斯密碼。"
        "現在，小隊請分成人數相同（或是最多差1個人）的兩組，一組負責發出訊號，一組負責接收訊號並解碼。"
        "發訊號的方式只能使用拍手，以長拍與短拍來表示長音與短音，"
        "不能發出任何聲音（講話、嗶聲等都不行），也不能做出拍手以外的手勢或動作。"
        "題目是一個英文單字，請參照上方的對照表來進行訊號發送／解密。"
        "在你們準備好後，隨隊人員會給發出訊號組的看題目，結束後解密組必須完整地將題目的單字拼出，"
        "如果差一個字母就任務失敗。",
    ),
    "幸福站任務": (
        "幸福好滋味",
        "「下一站，幸福」是很多人喜歡在搭捷運時拍下的環狀線車內顯示器的畫面。"
        "現在，你們已在幸福站下車，即將尋找幸福的好滋味。"
        "要找的是招牌上有「幸福」二字的餐廳、便利商店、超市，或任何有賣食物的店家。"
        "**請先在捷運站內宣告你們要找到幾家，這個數字送出之後就不能更改。**"
        "宣告完之後移動到站外，隨隊人員會倒數計時，從那一刻起限時10分鐘。"
        "如果在時間內找滿你們宣告的家數，可獲得「宣告家數 × 12」的代幣；"
        "**但如果只找到比宣告還少的家數，不論只差一家，都算任務失敗，一枚代幣都拿不到。**"
        "所以不要貪心，先想清楚再喊。"
        "另外，尋找過程中全程禁止使用手機。",
    ),
    "頂溪站任務": (
        "豆漿的起點",
        "應該很多人都有吃過永和豆漿，而永和豆漿一切的起源，就在頂溪站附近的世界豆漿大王。"
        "請找到世界豆漿大王的店面，並在店門口全隊合照！"
        "此任務過程中禁止使用手機，但可以問路人，或是四處搜尋來找出店家的位置。",
    ),
    "小碧潭任務": (
        "躺平也是一種任務",
        "大部分台大人應該都對小碧潭站和小碧潭支線有著複雜的心情——"
        "因為它，綠線區間車只能開到台電大樓站，班距還超長！"
        "不過，小碧潭還是有很多好逛的地方，像是最具代表性的 IKEA。"
        "社遊玩到現在，應該也累了吧，IKEA 正好是個可以休息的地方！"
        "請所有組員在 IKEA 裡面找到床或沙發，並且**同時**躺下休息，"
        "全隊都躺好的那一刻才算成功（可以分散在不同的床或沙發上）。",
    ),
    "圓山花博公園任務": (
        "巨人的椅子",
        "花博是 2010 年在台北舉辦的一場盛大活動，花博公園圓山園區就是當時的展區之一，"
        "至今仍留有許多漂亮的裝置藝術。"
        "請找到一件名為「巨人坐著整個月」的裝置藝術（提示：它大部分是黃色的），"
        "你們可以在它前面觀察任意長的時間，觀察完成後請告知隨隊人員。"
        "接著，全隊必須背對該裝置藝術，隨隊人員會問你們三個關於它的問題，三題都答對才算任務成功。"
        "回答過程中禁止偷看或使用手機，否則任務失敗。",
    ),
    "石牌站任務": (
        "石碑變石牌",
        "你們現在所在的「石牌」，地名其實來自一塊石碑。"
        "清乾隆年間（約 1745–1748 年），漳州移民在開墾北投一帶時，"
        "常與原本生活在這片土地上的原住民（凱達格蘭族）發生土地糾紛，"
        "淡水同知曾日瑛於是立下界碑，劃分漢人與原住民的田地，"
        "碑上刻著「奉憲分府曾批斷東南勢田園歸番管業界」。"
        "久而久之，「石碑」被鄉人讀成了「石牌」，就成了今天的地名。"
        "其中一座界碑，現在就立在石牌站前的廣場上。\n\n"
        "現在，隨隊人員會出 10 題關於台灣原住民的知識問答，全部都是簡答題。"
        "**請先預測你們能答對幾題，這個數字送出後就不能更改。**"
        "如果答對的題數達到你們的預測，就可以獲得「預測題數 × 4」的代幣；"
        "**只要答對的題數比預測少，任務就失敗，一枚代幣都拿不到。**"
        "作答時可以全隊討論，但每題只能給一個答案，並且全程禁止使用手機。",
    ),
    "饒河夜市任務": (
        "差一點就保夾",
        "歡迎來到饒河夜市！你們到的時間應該不是夜市人潮最多的時候，可能沒什麼吃的，"
        "但這裡仍然有很多夾娃娃機可以玩。"
        "對於非專業人士來說，想要用低成本夾到娃娃，一個不錯的方法就是找到已經被投入很多錢、"
        "距離保夾不遠的機台。\n\n"
        "要找的是「**已投入金額至少是保夾金額一半**」的夾娃娃機。"
        "**請先預測你們能找到幾台，這個數字送出之後就不能更改。**"
        "接著限時 10 分鐘，如果找到的台數達到你們的預測，就可以獲得「預測台數 × 4」的代幣；"
        "**只要找到的台數比預測少，任務就失敗，一枚代幣都拿不到。**\n\n"
        "規則：\n"
        "・**全隊必須和隨隊人員一起行動，不可以分頭找**，"
        "每找到一台都要當場讓隨隊人員親眼看到機台上的金額才算數。\n"
        "・禁止自己投錢。\n"
        "・每一家店只能進出一次，重複進出的店家，裡面找到的機台一律不算。",
    ),
    "北投圖書館任務": (
        "借一本溫泉",
        "北投圖書館是台灣最美麗的圖書館之一，而北投也以溫泉聞名。"
        "現在，請成功借到一本**書名**含有「溫泉」的書"
        "（其他語言的也算，例如 hot spring、日文的「温泉」）。"
        "必須是書名，封面上的其他敘述不算。"
        "如果沒有借書證，趕快辦一個吧！",
    ),
    "天台廣場任務": (
        "跟著兔子走",
        "歡迎來到天台廣場！走進這棟樓之後，你們大概就會明白，為什麼大家都說它很「鬼」。"
        "在《愛麗絲夢遊仙境》裡，愛麗絲就是追著一隻兔子，才掉進兔子洞、闖進那個奇怪的世界——"
        "在這棟一樣有點奇怪的大樓裡，今天換你們去找兔子了。\n\n"
        "請在天台廣場大樓裡面找到如圖的這隻兔子！"
        "要找的是如圖的**立體實物**，海報、招牌之類的平面設計不算。限時 10 分鐘。",
    ),
    "蘆洲捷運公園任務": (
        "吊環練習生",
        "搭了一整天的捷運，你們應該拉了不少吊環吧！今天在蘆洲捷運公園，要來點真的。\n\n"
        "請找到如圖的設施，推派一名代表進行單槓懸掛（高度可以自己選）。"
        "**懸掛前請先預測能撐多久，最少 30 秒、最多 60 秒，這個數字送出之後就不能更改。**"
        "如果撐到預測的秒數，就可以獲得「預測秒數 × 0.5」的代幣（四捨五入）；"
        "**只要沒撐到預測的秒數，任務就失敗，一枚代幣都拿不到。**",
    ),
    "新北大都會公園任務": (
        "滑進大都會",
        "新北大都會公園位在三重、五股、蘆洲交界的二重疏洪道裡，面積 424 公頃，是新北市最大的公園。"
        "它原本叫「大臺北都會公園」，因為常常被誤以為在台北市，2019 年才改成現在的名字；"
        "自 2018 年起，這裡也是新北燈會的主場地。\n\n"
        "請所有組員輪流從辰光橋的滾輪溜滑梯溜下來（位置提示：在機捷三重站的出口旁），"
        "全隊都溜完就算成功！",
    ),
    "三創任務": (
        "首頁換成星雨",
        "三創和隔壁的光華商場是科技宅的天堂，其中三創的一樓就展示了許多筆電。"
        "請把任意一台筆電、任意一個瀏覽器的首頁，設成星雨 FB 粉專的連結，"
        "並且關掉再重新打開瀏覽器，驗證是否設定成功。"
        "如果怕被陌生人看到星雨的粉專會很尷尬，可以在成功之後把它改回來。",
    ),
    "林本源園邸任務": (
        "園子裡的那幾個字",
        "歡迎來到林本源園邸，又稱板橋林家花園。林家於1847年在此設立租館，"
        "林國華、林國芳兄弟自1851年起興建三落大厝，花園部分則於1853年完成。"
        "板橋林家靠米業與鹽務成為清代臺灣的巨商，第三代林維源更曾協助臺灣巡撫劉銘傳推動撫墾與商務。"
        "這座園林仿蘇州留園設計，是目前臺灣僅存最完整的園林建築，並於1985年被指定為國定古蹟。"
        "現在，請在門口看完這個題字，把他記住，收起手機進入林本源園邸，並在10分鐘內找到他。",
    ),
}

# name -> admin_notes. The answer key / judging reference for whoever
# approves that challenge's challenge_result request (a team admin, or the
# super admin acting as backup approver) — rendered right on the approval
# card (see routers/admin.py's /challenges and TeamAdminPage.tsx). Never
# reaches a team: absent from ChallengeTeaser and from the team-scoped
# detail endpoint (see models.py's ChallengeAdminView docstring).
_ADMIN_NOTES: dict[str, str] = {
    "台大二活任務": (
        "請告訴大家幾點幾分要回到樓下集合，如果超時5分鐘有人還沒回來就算是任務失敗"
        "社團是否存在二活，逐一詢問時對照：\n自閉星雨服務團(有，10F，答錯你就可以退社了)\n 卡通漫畫研究社(無，社辦在一活)\n"
        "臺灣韓國學生交流會(無，只有臺灣日本學生交流會)\n 熱音社(無，只有椰風搖滾)\n"
        "綺巧手工藝社(有，9F)\n 日本麻雀研究社(有)\n 登山社(無，社辦在一活)\n"
    ),
    "建成圓環任務": (
        "確認是否在建成圓環（南京西路與重慶北路口）。隊伍喊出的目標數字須介於30~100之間；"
        "* 代表該數字是6的倍數、8的倍數，或數字中包含6或8，該次應該拍手而不是喊數字，"
        "只要對照到隊伍指定的目標數字那一格即可，不必整份都看：\n"
        "1 2 3 4 5 * 7 * 9 10\n"
        "11 * 13 14 15 * 17 * 19 20\n"
        "21 22 23 * 25 * 27 * 29 *\n"
        "31 * 33 34 35 * 37 * 39 *\n"
        "41 * 43 44 45 * 47 * 49 50\n"
        "51 52 53 * 55 * 57 * 59 *\n"
        "* * * * * * * * * 70\n"
        "71 * 73 74 75 * 77 * 79 *\n"
        "* * * * * * * * * *\n"
        "91 92 93 94 95 * 97 * 99 100"
    ),
    "西門町任務": (
        "接受「高松燈」或「天王寺璃奈」任一位角色的周邊，兩者皆可判成功；"
        "確認：商品上沒有其他角色圖案、價格在300元（含）以內。"
    ),
    "葫洲站任務": "正確店家：ieat早午餐（真極品牛肉麵）。找錯家直接判失敗，只有一次機會。",
    "明曜百貨任務": (
        "地點：明曜百貨11樓卡通尼樂園。開始前發6枚代幣給隊伍。\n"
        "並沒有限制只能一個人玩，可以多人合作、一人負責一個踏板。\n"
        "判斷過關：第3首歌結束後畫面顯示「STAGE CLEARED」，且評等不是 E 等。\n"
        "判斷失敗：畫面顯示「STAGE FAILED」，或評等為 E 等。\n"
        "另外確認曲名含有「星」「雨」「star」或「rain」（大小寫不拘），選錯歌直接失敗。"
    ),
    # The judging admin's approval card shows admin_notes but NOT the task
    # description, so for a checklist-style judgment the criteria have to be
    # repeated here or the admin has nothing to check against.
    "松山機場任務": (
        "看影片逐項確認，三項都要有才算成功：\n"
        "1. 飛機在地上行走至少3秒鐘\n"
        "2. 飛機離地的瞬間\n"
        "3. 飛機在畫面上的高度超過視野前方的山脈"
    ),
    "木柵機廠任務": (
        "入庫的定義：整部列車完整的進入車庫。\n"
        "出庫的定義：整部列車完整駛出車庫。\n"
        "如果同時發生，則請比較完整駛出／駛入的時間點來判斷。\n"
        "車型辨識：馬特拉車號2位數、龐巴迪車號3位數。\n"
        "猜錯可以繼續等下一列車再猜，直到猜中為止（不會因為猜錯就直接失敗）。"
    ),
    "辛亥國小任務": (
        "共投10球，進7球（含）以上算成功，未達7球失敗。\n"
        "必須依隊伍事先宣告的順序輪流投；宣告開始挑戰後就不能再練習。"
    ),
    "美麗華任務": (
        "開始前請記下隊伍喊出的趟數和接力順序（例如 A→B→C）。\n"
        "全隊照順序輪流跑，輪完一輪再從第一位開始；順序全程不能改，跑錯順序就算失敗。\n"
        "一趟 = 從地面層爬到摩天輪所在樓層再回到地面，沒摸到那一層就折返不算。\n"
        "限時10分鐘，全部趟數跑完才算成功；超時或有一趟沒完成都算失敗。"
    ),
    "南港區民活動中心任務": (
        "題目單字：asperger（請只給發訊號組看，不要讓解碼組看到）。\n"
        "解碼組必須完整拼出 asperger，差一個字母就算失敗。\n"
        "過程中發訊號組只能用拍手（長拍／短拍）傳訊號，不得發出任何聲音，也不得有拍手以外的手勢或動作。"
    ),
    "台北地下街任務": "正確答案：825公尺。誤差在100公尺（含）以內都算成功。",
    "頂埔站任務": (
        "允許隊伍用手機查三鶯線時刻表，但請不要主動提醒他們可以這樣做。\n"
        "沒有固定答案：請先記下隊伍在板南線月台上喊出的預測時間（例如 3分30秒），"
        "接著全隊一起走到三鶯線驗票閘門旁，以「第一眼看到」的三鶯線發車等候時間為準，"
        "誤差在1分鐘（含）以內算成功。移動途中不得更改預測時間。"
    ),
    "幸福站任務": (
        "請叫大家到站外，並且喊 3、2、1 開始計時；開始計時後大家才能開始移動。\n"
        "限時10分鐘內找到隊伍宣告的店家數，達標才算成功。\n"
        "認定標準：招牌上要有「幸福」二字，餐廳、便利商店、超市或任何有賣食物的店家都算。\n"
        "計時開始後全程禁止使用手機，請留意有沒有人偷看。"
    ),
    "頂溪站任務": (
        "世界豆漿大王：新北市永和區永和路二段 284 號（出發前請自己再確認一次位置）。\n"
        "合照要拍得到店家招牌，且全隊都要在照片裡。\n"
        "過程中禁止使用手機，可以問路人。"
    ),
    "小碧潭任務": (
        "全隊必須同時躺下：隨隊人員看到所有人在同一時間都躺著，才算成功"
        "（可以分散在不同的床或沙發上，不必擠同一張）。\n"
        "請提醒大家遵守店內規定、保持禮貌，不要影響其他客人。"
    ),
    "圓山花博公園任務": (
        "隊伍說「觀察完成」後才開始問，開始後全隊背對裝置藝術，有人回頭或用手機就判失敗。\n"
        "三題都要答對：\n"
        "1. 總共有多少張椅子？ → 26 張\n"
        "2. 有些椅子上有 1–30 的大編號，但缺了其中 2 個數字，是哪兩個？ → 14、15\n"
        "3. 椅背共有 3 種顏色：棕色、橘紅色、綠色，請依數量由多到少排列。 → 棕、橘紅、綠"
    ),
    "石牌站任務": (
        "開始前先確認隊伍預測的題數（1–10）。\n"
        "**一律從寬認定**：簡答題意思對了就算，錯字、音近、族名的常見別稱或舊稱都算對。\n"
        "**不必十題全部問完，出現以下任一情況就可以直接停止：**\n"
        "・已答對題數 ≥ 預測題數 → 確定成功\n"
        "・已答對題數 ＋ 剩下還沒問的題數 ＜ 預測題數 → 確定失敗\n"
        "例：預測 7 題，問完第 6 題時答對 2 題、答錯 4 題，剩下 4 題全對也只有 6 題 → 直接判失敗。\n\n"
        "1. 台灣原住民族的語言，屬於哪一個語系？ → 南島語系\n"
        "2. 台灣人口最多的原住民族是哪一族？ → 阿美族\n"
        "3. 居住在蘭嶼的原住民族是哪一族？ → 達悟族（答雅美族也算對）\n"
        "4. 達悟族傳統上用木板拼接、不用鐵釘打造的船，叫做什麼？ → 拼板舟\n"
        "5. 「矮靈祭」是哪一族的祭典？ → 賽夏族\n"
        "6. 「八部合音」（祈禱小米豐收歌）是哪一族的傳統歌謠？ → 布農族\n"
        "7. 1930 年霧社事件的領導人莫那・魯道，屬於哪一族？ → 賽德克族"
        "（答泰雅族也算對，賽德克族在 2008 年以前被歸在泰雅族底下）\n"
        "8. 主要分布在阿里山一帶的原住民族是哪一族？ → 鄒族\n"
        "9. 世居日月潭周邊的原住民族是哪一族？ → 邵族\n"
        "10. 每年的「原住民族日」是幾月幾日？ → 8 月 1 日\n\n"
        "備用題（某題有爭議時替換）：\n"
        "A. 石牌一帶原本是哪一族原住民的生活範圍？ → 凱達格蘭族（任務敘述裡有提到）\n"
        "B. 「猴祭」是哪一族的祭典？ → 卑南族"
    ),
    "饒河夜市任務": (
        "開始前先確認隊伍預測的台數。限時 10 分鐘。\n"
        "**全隊必須跟你一起移動，不可以分頭找。**有人脫隊自己去別家店找的話，"
        "那個人找到的機台不算，並請立刻叫他歸隊。\n"
        "**請想辦法記下看過的店家和機台**（例如拍照或寫下店名＋機台位置），避免重複計算。"
        "同一家店重複進出的話，那家店的機台一律不算。\n"
        "每一台都要你親眼看到機台上的「保夾金額」和「已投入金額」，已投入 ≥ 保夾的一半才算；"
        "機台上看不到這兩個數字的不算。隊員不得自己投錢。\n"
        "**確定成功（找到的台數已達預測）就可以直接停止，不用把 10 分鐘跑完。**"
        "失敗則要等時間到才能確定。"
    ),
    "北投圖書館任務": (
        "判定標準：**以借書收據（或借閱紀錄）上印的書名為準**，書名裡有「溫泉」或其他語言的同義詞"
        "（hot spring、温泉、onsen 等）就算成功。封面上的宣傳文字、作者名等不算。\n"
        "沒有借書證的話要當場辦，辦證通常要帶證件——請提醒大家帶，或至少確定隊上有人有借書證。\n"
        "借出來的書之後要記得還，跟借書的人確認好誰負責還書。"
    ),
    "天台廣場任務": (
        "答案位置：6F U2 電影院門口。\n"
        "**任務開始後請立即計時 10 分鐘。**\n"
        "只有找到如圖的立體實物才算，海報、招牌圖案等平面設計不算。"
    ),
    "蘆洲捷運公園任務": (
        "開始前確認預測秒數（30–60）和代表是誰。只能一個人、只能挑戰一次。\n"
        "計時從代表雙手握住單槓、雙腳離地開始，腳碰到地面或手鬆開就停。\n"
        "**撐到預測的秒數就可以直接判成功、叫他下來**，不用繼續撐。\n"
        "請注意安全，懸掛時旁邊要有人照看。"
    ),
    "新北大都會公園任務": (
        "全隊每一個人都要從滾輪溜滑梯溜下來一次，才算成功。\n"
        "公共設施，請大家守規矩排隊，遇到小朋友請讓他們先玩。"
    ),
    "三創任務": (
        "星雨粉專網址：【請填入】\n"
        "驗證方式：在你面前把瀏覽器整個關掉再重新打開，首頁直接出現星雨粉專才算成功。\n"
        "主辦人幾個月前已經把部分電腦的 Microsoft Edge 首頁設成 rickroll，"
        "所以如果他們被瑞克搖了，可以跟他們說是主辦人搞的 XD"
    ),
    "林本源園邸任務": (
        "計時在所有人都踏進去林本源園邸之後才開始，限時10分鐘內找到題字的所在位置。\n"
        "不確定是否需要門票；如果需要，請帶大家拿著學生證去售票口兌換免費的票。"
    ),
}

# name -> image_url. A reference photo shown alongside the task description —
# hidden until a team's attempt is approved to start, same as description
# itself (see ChallengeTeaser vs. Challenge in models.py) — so it must show
# what to look for (a DDR cabinet, a character), never the actual
# venue/answer. Files live in frontend/public/challenge-images/ (see the
# README there) and are served at this exact path by the built SPA.
_IMAGES: dict[str, str] = {
    "明曜百貨任務": "/challenge-images/ddr-machine.png",
    "西門町任務": "/challenge-images/takamatsu-tomori.png",
    "美麗華任務": "/challenge-images/miramar-stairs.jpg",
    # The Morse reference chart the team decodes against — it *is* task
    # material here, not just a hint, so the team needs it on screen.
    "南港區民活動中心任務": "/challenge-images/morse-code.jpg",
    # The inscription the team memorises at the gate and then hunts for —
    # task material, like the Morse chart above, not just a hint.
    "林本源園邸任務": "/challenge-images/lin-garden-inscription.jpg",
    # The description says 左圖 = 馬特拉 / 右圖 = 龐巴迪, and the modal renders
    # image_url then image_url_2 side by side in that order — so these two
    # can't be swapped without rewriting the description.
    "木柵機廠任務": "/challenge-images/matra-train.jpg",
    # The rabbit to find and the bar to hang from — both task material.
    "天台廣場任務": "/challenge-images/tiantai-rabbit.jpg",
    "蘆洲捷運公園任務": "/challenge-images/luzhou-bar.jpg",
}

# name -> second reference photo (optional), rendered to the right of
# _IMAGES' photo. See models.py's Challenge.image_url_2 docstring.
_IMAGES_2: dict[str, str] = {
    "西門町任務": "/challenge-images/tennoji-rina.png",
    "木柵機廠任務": "/challenge-images/bombardier-train.jpg",
}

# Manual coordinate corrections, keyed by (map-visible) challenge name —
# takes priority over the lat/lng baked into _CHALLENGES below. Same idea as
# seed_stations.py's _COORD_OVERRIDES: generate entries with the superadmin
# "任務管理" tab's 任務座標 mode — pick a challenge, drag/click its marker to
# the right spot, then use its 輸出 button to get a properly-formatted entry
# to paste in here.
_COORD_OVERRIDES: dict[str, tuple[float, float]] = {
    "木柵機廠任務": (25.001748, 121.584985),
    "松山機場任務": (25.064416, 121.550315),
    "頂埔站任務": (24.959737, 121.419616),
    "明曜百貨任務": (25.041225, 121.552058),
    "辛亥國小任務": (25.006418, 121.558877),
    "南港區民活動中心任務": (25.053535, 121.607956),
}

# name, type, reward_config, location_name, lat, lng, initial_pool_state
#
# Placeholder landmark challenges (36 of them, TBD reward-only entries) have
# been removed — every challenge here now has real, written content. The 3
# "active" ones below keep the map from being empty before a superadmin ever
# touches anything. (They used to all be type='fixed', so a team's first
# sight of the pool was never a call-your-shot/steal mechanic — 明曜百貨任務
# becoming 'variable' ends that; there are only two fixed challenges left, so
# the rule can't hold as stated.) The rest start 'queued' and enter play via
# activate_initial_pool()/_refill_pool() in game_logic.py.
_CHALLENGES: list[tuple] = [
    ("台大二活任務", "fixed", {"chips": 27}, "台大二活門口", 25.012938045228722, 121.53662176506363, "queued"),
    ("西門町任務", "fixed", {"chips": 11}, "西門站5號出口", 25.04286, 121.5088, "active"),
    ("建成圓環任務", "variable", {"chips_per_unit": 0.3, "unit_label": "數字"}, "建成圓環", 25.0534, 121.5153, "queued"),
    ("台北地下街任務", "steal", {"steal_pct": 25}, "台北地下街Y1出口", 25.04886, 121.51906, "queued"),

    ("葫洲站任務", "fixed", {"chips": 28}, "葫洲站", 25.072610389433837, 121.60702478470597, "active"),
    ("美麗華任務", "variable", {"chips_per_unit": 2.5, "unit_label": "趟"}, "美麗華百樂園", 25.083694238417248, 121.557050674598, "queued"),
    ("明曜百貨任務", "variable", {"chips_per_unit": 3, "unit_label": "等級"}, "明曜百貨11樓", 25.041351036032598, 121.55073436774637, "active"),
    # Both nudged ~50m off their station's point (頂埔站 24.959634,
    # 121.419375 / 幸福站 25.049973, 121.460016 — the effective coordinates
    # seed_stations.py gives them) so the pin doesn't sit on top of the
    # station dot. Refine with the superadmin 任務座標 tool if you want them
    # on an exact spot.
    ("頂埔站任務", "steal", {"steal_pct": 35}, "頂埔站板南線月台", 24.959384, 121.419825, "queued"),
    ("幸福站任務", "variable", {"chips_per_unit": 12, "unit_label": "店家"}, "幸福站", 25.049723, 121.460466, "queued"),
    # APPROXIMATE COORDINATES — everything below is rounded to 4 decimals on
    # purpose so it doesn't read as surveyed. Replace each with the real spot
    # before the event, either here or via the superadmin 任務座標 tool.
    ("南港區民活動中心任務", "steal", {"steal_pct": 35}, "南港區民活動中心門口階梯處", 25.0530, 121.6060, "queued"),
    ("松山機場任務", "fixed", {"chips": 17}, "松山機場3F觀景台", 25.0629, 121.5518, "queued"),
    ("木柵機廠任務", "fixed", {"chips": 33}, "木柵機廠", 24.9980, 121.5810, "queued"),
    ("辛亥國小任務", "steal", {"steal_pct": 65}, "辛亥國小風雨籃球場", 25.0045, 121.5565, "queued"),
    ("林本源園邸任務", "fixed", {"chips": 21}, "林本源園邸", 25.0113, 121.4549, "queued"),
    # Each nudged ~50-150m off its station's point toward where the task
    # actually happens, so the pin doesn't cover the station dot.
    ("頂溪站任務", "fixed", {"chips": 15}, "頂溪站2號出口", 25.0131, 121.5162, "queued"),
    ("小碧潭任務", "fixed", {"chips": 20}, "IKEA新店店", 24.9712, 121.5316, "queued"),
    ("圓山花博公園任務", "steal", {"steal_pct": 50}, "花博公園圓山園區", 25.0710, 121.5222, "queued"),
    ("石牌站任務", "variable", {"chips_per_unit": 4, "unit_label": "題"}, "石牌站1號出口", 25.1140, 121.5162, "queued"),
    ("三創任務", "fixed", {"chips": 11}, "三創生活園區1F", 25.0458, 121.5313, "queued"),
    ("饒河夜市任務", "variable", {"chips_per_unit": 4, "unit_label": "台"}, "饒河街觀光夜市東側入口", 25.0507, 121.5767, "queued"),
    ("北投圖書館任務", "fixed", {"chips": 27}, "臺北市立圖書館北投分館", 25.1363, 121.5064, "queued"),
    # 天台廣場 / 蘆洲捷運公園: I couldn't pin these down from public sources —
    # both pins are guesses (西門 side of 中華路; near 三民高中站, which is
    # where one property listing places the park). Fix with 任務座標.
    ("天台廣場任務", "fixed", {"chips": 8}, "天台廣場", 25.0432, 121.5093, "queued"),
    ("蘆洲捷運公園任務", "variable", {"chips_per_unit": 0.5, "unit_label": "秒"}, "蘆洲捷運公園", 25.0852, 121.4740, "queued"),
    # The Airport MRT isn't in the station network, so the sim reaches this
    # via 中和新蘆線 三重 — the two are a short out-of-station transfer apart.
    ("新北大都會公園任務", "fixed", {"chips": 17}, "機捷三重站", 25.0566, 121.4830, "queued"),
]


async def seed(conn) -> None:
    """Idempotent upsert by `name`. `pool_state` is intentionally absent from
    the ON CONFLICT SET clause — only set on first INSERT — so redeploying
    mid-event never resets a challenge that's already gone active/retired.

    `name` is the map-visible title (location-flavored only, e.g. "饒河街任務")
    — `inner_title` is the real/flavor title, hidden alongside `description`
    until a team's attempt is approved to start."""
    for name, ctype, reward_config, location_name, lat, lng, initial_state in _CHALLENGES:
        inner_title, description = _CONTENT.get(name, (TBD, TBD))
        lat, lng = _COORD_OVERRIDES.get(name, (lat, lng))
        image_url = _IMAGES.get(name)
        image_url_2 = _IMAGES_2.get(name)
        admin_notes = _ADMIN_NOTES.get(name, "")
        await conn.execute(
            """INSERT INTO challenges (name, inner_title, description, type, reward_config, location_name, lat, lng, image_url, image_url_2, admin_notes, pool_state)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
               ON CONFLICT (name) DO UPDATE
               SET inner_title = EXCLUDED.inner_title, description = EXCLUDED.description, type = EXCLUDED.type,
                   reward_config = EXCLUDED.reward_config, location_name = EXCLUDED.location_name,
                   lat = EXCLUDED.lat, lng = EXCLUDED.lng, image_url = EXCLUDED.image_url,
                   image_url_2 = EXCLUDED.image_url_2, admin_notes = EXCLUDED.admin_notes""",
            name, inner_title, description, ctype, json.dumps(reward_config), location_name, lat, lng, image_url,
            image_url_2, admin_notes, initial_state,
        )

    # Anything in the DB that's no longer listed above (e.g. the placeholder
    # landmark challenges this file used to seed) is actually deleted, not
    # just retired — schema.sql points every table that can reference a
    # challenge (challenge_attempts, approval_requests, action_log) at it
    # with either ON DELETE CASCADE or SET NULL, so this can't fail on a
    # dangling reference even if that placeholder was already attempted.
    seeded_names = [name for name, *_ in _CHALLENGES]
    await conn.execute(
        "DELETE FROM challenges WHERE NOT (name = ANY($1::text[]))",
        seeded_names,
    )
