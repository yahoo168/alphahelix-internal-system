// 使用事件委托为所有 .follow-item 元素绑定点击事件
function handleFollowItem(apiUrl) {
  // 初始化 DataTable，设置每页显示 50 条记录
  var table = $("#Table").DataTable({
    paging: true, // 启用分页
    ordering: true, // 启用排序
    info: true, // 启用表格信息
    searching: true, // 启用搜索
    pageLength: 50, // 设置每页显示 50 条记录
  });

  $(document).on("click", ".follow-item", function () {
    var itemId = $(this).data("item_id"); // 获取 item_id
    var isFollowing = $(this).hasClass("bi-suit-heart-fill"); // 检查当前状态
    var clickedIcon = $(this); // 显式获取被点击的元素

    if (isFollowing) {
      clickedIcon
        .removeClass("bi-suit-heart-fill heart-red")
        .addClass("bi-suit-heart");

      // 更新 followers_num
      var followerNumElem = $("#follower_num_" + itemId);
      var currentFollowers = parseInt(followerNumElem.text());
      followerNumElem.text(currentFollowers - 1);

      // 更新 Follow 列的 data-sort 属性
      clickedIcon.closest("td").attr("data-sort", "0");

      // 更新 Followers 列的 data-sort 属性
      followerNumElem.closest("td").attr("data-sort", currentFollowers - 1);
    } else {
      clickedIcon
        .removeClass("bi-suit-heart")
        .addClass("bi-suit-heart-fill heart-red");

      // 更新 followers_num
      var followerNumElem = $("#follower_num_" + itemId);
      var currentFollowers = parseInt(followerNumElem.text());
      followerNumElem.text(currentFollowers + 1);

      // 更新 Follow 列的 data-sort 属性
      clickedIcon.closest("td").attr("data-sort", "1");

      // 更新 Followers 列的 data-sort 属性
      followerNumElem.closest("td").attr("data-sort", currentFollowers + 1);
    }

    // 强制 DataTables 重新计算排序并刷新表格
    var row = clickedIcon.closest("tr");
    table.row(row).invalidate().draw(false); // 使该行无效并重新读取数据，保留当前分页

    // 发送 AJAX 请求到后端
    $.ajax({
      url: apiUrl,
      type: "POST",
      contentType: "application/json", // 指定内容类型为 JSON
      data: JSON.stringify({
        item_id: itemId, // 将数据序列化为 JSON
        follow_status: !isFollowing, // 传递相反的状态
      }),

      success: function (response) {
        if (response.status === "success") {
          // 切换 class
        } else {
          alert("状态更新失败");
        }
      },
      error: function () {
        alert("请求失败");
      },
    });
  });
}

// Function to convert URLs in the text into clickable links
function linkifyText(text) {
  // 改进的正则表达式，匹配以 http 或 https 开头的 URL，直到遇到空格、括号或中文字符
  // const urlPattern = /(https?:\/\/[^\s\]\[\)\(\u4e00-\u9fa5]+)/g;
  const urlPattern = /(https?:\/\/[^\s<]+)/g;
  // 替换找到的 URL 为 <a> 标签，生成超链接
  let linkedText = text.replace(urlPattern, function (url) {
    return '<a href="' + url + '" target="_blank">' + url + "</a>";
  });

  // 将文本中的换行符 \n 替换为 HTML 的 <br> 标签，以保持换行效果
  return linkedText.replace(/\n/g, "<br>");
}

// Function to convert sentences starting with "主題" into <h3> tags
function wrapSubject(text) {
  // 使用正则表达式查找以 "主題" 开头的句子，后面可跟随数字和中文标点符号，并将其替换为 <h3> 包裹的内容
  return text.replace(/(主題\d*：.*?)(<br>|$)/g, function (match, p1) {
    // 返回被 <h3> 包裹的 "主題" 部分
    return "<h5>" + p1 + "</h5>";
  });
}

function convertMarkdownText(ID) {
  // 使用 jQuery 獲取指定的 <p> 元素
  const $paragraph = $("#" + ID);

  if ($paragraph.length === 0) {
    console.error("Element with the given ID not found.");
    return;
  }

  // 獲取純文字內容
  let text = $paragraph.text().trim(); // 移除兩端的空白字符以避免不必要的問題
  // 去除「```markdown」字串
  text = text.replace(/```markdown/g, "");
  text = text.replace(/```/g, "");

  // 替換 **粗體** 或 __粗體__
  text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/__(.*?)__/g, "<strong>$1</strong>");

  // 替換 *斜體* 或 _斜體_
  text = text.replace(/\*(.*?)\*/g, "<em>$1</em>");
  text = text.replace(/_(.*?)_/g, "<em>$1</em>");

  // 替換 # 標題1 (h3)
  text = text.replace(/^# (.*)/gm, "<h3>$1</h3>"); // 確保匹配行首的 `#`

  // 替換 ## 標題2 (h4)
  text = text.replace(/^## (.*)/gm, "<h4>$1</h4>");

  // 替換 ### 標題3 (h5)
  text = text.replace(/^### (.*)/gm, "<h5>$1</h5>");

  // 將連續兩個或更多的 \n 替換為單個 \n
  text = text.replace(/\n{2,}/g, "\n");

  // 將文本拆分為每行並手動檢查每行
  let lines = text.split("\n");
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].startsWith("- ") && !lines[i - 1].match(/^<\/?h[1-6]>/)) {
      lines[i] = "<br>" + lines[i];
    }
  }

  // 將行重新合併成字符串
  text = lines.join("\n");

  // 更新段落的 HTML 內容
  $paragraph.html(text);
}

// 處理搜尋Ticker輸入事件的函數，包含模板生成邏輯
// 在頁面內須定義好id=suggestion-template的模板，供函數複製並填入suggestionsSelector
function TickerSearchSuggestion(
  inputSelector,
  suggestionsSelector,
  apiUrl,
  itemUrl
) {
  $(inputSelector).on("input", function () {
    let query = $(this).val();
    if (query.length > 0) {
      $.ajax({
        url: apiUrl,
        method: "GET",
        data: { query: query },
        success: function (data) {
          $(suggestionsSelector).empty(); // 清空建議列表
          if (data.length > 0) {
            data.forEach(function (item) {
              // 使用模板創建和填充建議項目
              let template = $("#suggestion-template").html(); // 從模板中獲取HTML
              let suggestionElement = $(template); // 使用 jQuery 創建新元素

              suggestionElement.find(".ticker-symbol").text(item.ticker); // 填充 ticker
              suggestionElement.find(".company-name").text(item.company_name); // 填充公司名稱
              suggestionElement.attr("data-ticker", item.ticker); // 設置 data-ticker 屬性
              suggestionElement.attr("data-company-name", item.company_name); // 設置 data-company-name 屬性
              //將ticker加入指定的URL
              let newItemUrl = itemUrl + item.ticker;
              suggestionElement.attr("href", newItemUrl); // 設置連結
              // 插入填充好的建議項目
              $(suggestionsSelector).append(suggestionElement);
            });
          }
        },
        error: function (xhr, status, error) {
          console.error("搜尋建議請求失敗: ", error);
        },
      });
    } else {
      $(suggestionsSelector).empty(); // 如果輸入框為空，清空建議列表
    }
  });
}
