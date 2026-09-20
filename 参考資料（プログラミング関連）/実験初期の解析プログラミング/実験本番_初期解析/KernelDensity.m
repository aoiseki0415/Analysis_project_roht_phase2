%% カーネル密度推定

% これはx軸：RT, y軸：密度のプロットとする
%
% input
% - data: RT列など
% - h: window length -> バンド幅
% - time width ([0:2000]など) : いる？
% - win : 0 or 1 : 0:Rectangular, 1:Gaussian
%
% output
% - dist

% 追加要件
% 窓をガウシアンにできるように
% →別の関数を作ることにする。そのほうが適切だよな。


function dist = KernelDensity(data,h,tm_width,win)

if length(data(:,1)) > length(data(1,:))
    data = data';
end
if length(tm_width(:,1)) > length(tm_width(1,:))
    tm_width = tm_width';
end

dist = zeros(1,length(tm_width));

tm_idx = 1;
for tm = tm_width
    
    switch win
        case 0 % Rectangular window
            pnow = length(data(data>1+tm-h/2 & data<tm+h/2)) / length(data) / h;
            
        case 1 % Gaussian window
            pnow = sum(exp(-1*(((data-tm)./h).^2)./2)*1./sqrt(2*pi)) /length(data) / h;
            % 上記であるデータポイントに対する密度を推定完了
    end
    
    dist(tm_idx) = pnow;
    
    tm_idx = tm_idx + 1;
end

end
