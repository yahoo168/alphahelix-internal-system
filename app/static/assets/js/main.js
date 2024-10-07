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