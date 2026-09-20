% 解析する被験者番号を指定する。追加・削除はこのリストだけを編集する。
participant_ids = {'101', '104', '106'};

% RT分布の計算・表示パラメータ
block_numbers = 1:6;
lwin = 30;
timewidth = 1:1:2000;

% 入出力の親フォルダ
dataRoot = "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験本番_初期解析";
resultRoot = '/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/ドキュメント/MATLAB/sandboxロート案件2/実験本番_初期解析/結果/RT関連';

for participant_index = 1:numel(participant_ids)
    participant_id = participant_ids{participant_index};

    % 指定被験者のbehaveフォルダを取得する。
    participantFolder = fullfile(dataRoot, participant_id);
    dateFolders = dir(participantFolder);
    dateFolders = dateFolders([dateFolders.isdir] & ...
        ~ismember({dateFolders.name}, {'.', '..'}));

    if numel(dateFolders) ~= 1
        error('被験者%sの日付フォルダを一意に特定できません。', participant_id);
    end

    folderPath = fullfile(participantFolder, dateFolders.name, 'behave');
    if ~isfolder(folderPath)
        error('被験者%sのbehaveフォルダが見つかりません: %s', participant_id, folderPath);
    end

    resultPath = fullfile(resultRoot, ['ID' participant_id]);
    if ~isfolder(resultPath)
        mkdir(resultPath);
    end

    %% 解析フェーズ: 6ブロック分のRTとmistouch数を先に読み込む
    blockResults = repmat(struct( ...
        'block_num', [], 'trial_numbers', [], 'raw_RT_data', [], 'RT_data', [], ...
        'density', [], 'miss_count', []), ...
        1, numel(block_numbers));

    for block_index = 1:numel(block_numbers)
        block_num = block_numbers(block_index);
        blockFile = dir(fullfile(folderPath, sprintf('*block%d_results.csv', block_num)));
        if numel(blockFile) ~= 1
            error('被験者%s: Block %dのresults.csvを一意に特定できません。', ...
                participant_id, block_num);
        end

        T = readtable(fullfile(blockFile.folder, blockFile.name));
        response_type = string(T.ResponseType);
        is_mistouch = response_type == "mistouch";

        % mistouchはRT推移図・外れ値基準・RT分布のすべてから除外する。
        % 3 SD外れ値とは異なり、RT推移図に空欄として残さない。
        raw_RT_data = T.RT_ms_(:);
        % CSVの行番号ではなく、記録されたtrial番号をx軸に用いる。
        % 同一trial内にmistouch記録が複数行ある場合でも、後続trialがずれない。
        trial_numbers = T.Trial(:);
        raw_RT_data = raw_RT_data(~is_mistouch);
        trial_numbers = trial_numbers(~is_mistouch);
        if all(isnan(raw_RT_data))
            error('被験者%s: Block %dに有効なRTがありません。', participant_id, block_num);
        end

        blockResults(block_index).block_num = block_num;
        blockResults(block_index).trial_numbers = trial_numbers;
        blockResults(block_index).raw_RT_data = raw_RT_data;
        blockResults(block_index).miss_count = sum(is_mistouch);
    end

    % 全6ブロックを基準に、RT平均 ± 3 SDの範囲外を外れ値として除外する。
    % 外れ値はNaNで残すため、RT推移図では該当trialが空欄になる。
    all_raw_RT = vertcat(blockResults.raw_RT_data);
    valid_raw_RT = all_raw_RT(~isnan(all_raw_RT));
    rt_mean = mean(valid_raw_RT);
    rt_sd = std(valid_raw_RT);
    rt_lower_limit = rt_mean - 3 * rt_sd;
    rt_upper_limit = rt_mean + 3 * rt_sd;

    for block_index = 1:numel(blockResults)
        RT_data = blockResults(block_index).raw_RT_data;
        is_outlier = RT_data < rt_lower_limit | RT_data > rt_upper_limit;
        RT_data(is_outlier) = NaN;
        valid_RT_data = RT_data(~isnan(RT_data));

        if isempty(valid_RT_data)
            error('被験者%s: Block %dは外れ値除外後に有効なRTがありません。', ...
                participant_id, blockResults(block_index).block_num);
        end

        density = KernelDensity(valid_RT_data, lwin, timewidth, 0);
        blockResults(block_index).RT_data = RT_data;
        blockResults(block_index).density = smoothdata(density, 'movmean', 50)';
    end

    % 外れ値除外後の全ブロック横断の最大値から、共通の縦軸上限を決める。
    all_RT = vertcat(blockResults.RT_data);
    all_RT = all_RT(~isnan(all_RT));
    all_density = vertcat(blockResults.density);
    rt_ymax = max(all_RT) * 1.2;
    density_ymax = max(all_density) * 1.2;

    %% 図作成フェーズ: 共通の縦軸上限を用いて6ブロック分を保存する
    for block_index = 1:numel(blockResults)
        block_num = blockResults(block_index).block_num;
        trial_numbers = blockResults(block_index).trial_numbers;
        RT_data = blockResults(block_index).RT_data;
        y = blockResults(block_index).density;
        miss_count = blockResults(block_index).miss_count;
        x = timewidth(:)';
        x_fill = [x, fliplr(x)];
        y_fill = [y', zeros(1, numel(y))];

        % RT推移図
        figure1 = figure('Units', 'pixels', 'Position', [100 100 800 500], ...
            'PaperUnits', 'inches', 'PaperPosition', [0 0 8 5], ...
            'PaperSize', [8 5]);
        plot(trial_numbers, RT_data, 'LineStyle', '-', 'Color', [0.3, 0.3, 0.3], ...
            'LineWidth', 2);
        xticks([0 80 160 240 320]);
        xlim([0 320]);
        ylim([0 rt_ymax]);
        set(gca, 'FontSize', 20);
        ax = gca;
        ax.TickDir = 'out';
        ax.FontName = 'Arial';
        set(ax, 'Box', 'off');
        xlabel('trial', 'FontSize', 28);
        ylabel('Reaction Time (ms)', 'FontSize', 26);
        yticks(0:500:ceil(rt_ymax / 500) * 500);
        pngPath = fullfile(resultPath, ...
            sprintf('ID%s_Block%d_RT_trend.png', participant_id, block_num));
        print(figure1, pngPath, '-dpng', '-r150');

        pause(3);

        close(figure1);

        % RT分布図
        figure2 = figure('Units', 'pixels', 'Position', [100 100 800 500], ...
            'PaperUnits', 'inches', 'PaperPosition', [0 0 8 5], ...
            'PaperSize', [8 5]);
        fill(x_fill, y_fill, [0.3, 0.3, 0.3], ...
            'FaceAlpha', 0.3, 'EdgeColor', 'none');
        hold on
        plot(x, y, 'Color', [0.3, 0.3, 0.3], 'LineWidth', 3);
        xticks(0:500:2000);
        xlim([0 2000]);
        ylim([0 density_ymax]);
        set(gca, 'FontSize', 20);
        ax = gca;
        ax.YAxis.Exponent = -3;
        ax.LineWidth = 2;
        ax.TickDir = 'out';
        ax.FontName = 'Arial';
        set(ax, 'Box', 'off');
        xlabel('Reaction Time (ms)', 'FontSize', 28);
        ylabel('Density', 'FontSize', 28);
        text(0.9, 0.9, sprintf('Mistouch: %d', miss_count), ...
            'Units', 'normalized', 'HorizontalAlignment', 'right', ...
            'VerticalAlignment', 'top', 'FontSize', 18, 'FontName', 'Arial');
        pngPath = fullfile(resultPath, ...
            sprintf('ID%s_Block%d_RT_distribution.png', participant_id, block_num));
        print(figure2, pngPath, '-dpng', '-r150');

        pause(3);
        
        close(figure2);
    end
end
