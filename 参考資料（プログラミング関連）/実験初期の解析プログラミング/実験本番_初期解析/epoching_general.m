% function to make epochs from raw data
% input : data, cues->datapoints, zyn
%   ex) tim = [-500 1000]　cue から前後何秒かのデータをepochingしたいか←大事！
%   zyn: calculate z-score (0/1) 1の場合zscore計算
% output : チャンネル数分の部屋を持つセル配列を作成。部屋ごとに縦長データを横方向に格納していく

function [epoched_data] = epoching_general(data,cues,tim,zyn)
%cueは配列。cueが出た時の時刻を入力おく（20トライアルなら、20個）　cue-timing
% zynは0
% 脳波（縦長のデータ）

if length(data(:,1)) < length(data(1,:))
    data = data'; % 横長を縦長に
end

% nch = length(data(:,1));
ntr = length(cues);
maxchs = length(data(1,:));

epoched_data=cell(1,maxchs);


for ch = 1:maxchs
    epoched_data = zeros(tim(2)-tim(1),ntr);
    
    for tr = 1:ntr
        if zyn == 0
            epoched_data(:,tr) = data(cues(tr)+tim(1)+1:cues(tr)+tim(2),ch);
        else
            epoched_data(:,tr) = zscore(data(cues(tr)+tim(1)+1:cues(tr)+tim(2),ch));
        end
    end
end

end